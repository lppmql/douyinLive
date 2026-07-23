"""采集控制中心状态聚合。

页面只请求这一份状态，避免每张卡片各自轮询一套接口，既降低数据库压力，
也保证补齐动作、长期服务和后台自动同步看到的是同一个时间点。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.status import TaskStatus
from app.models.asr_tasks import AsrTask
from app.models.collector_module_states import CollectorModuleState
from app.models.scraper_tasks import ScraperTask
from app.services.collector.scheduler import scheduler_manager
from app.services.resources.asr_policy import build_asr_resource_plan
from app.services.sync.de_sync import pending_complete_session_count
from app.services.tasks.batch_runners import (
    pending_knowledge_session_count,
)
from app.services.tasks.control import CONTROL_TASK_TYPES, TASK_LABELS, TASK_TYPE_MODULES
from app.services.tasks.module_service import collector_module_service
from app.services.tasks.views import list_unified_tasks


ACTIVE_STATUSES = {TaskStatus.PENDING.value, TaskStatus.QUEUED.value, TaskStatus.RUNNING.value, TaskStatus.PROCESSING.value}


def _status_value(value: Any) -> str:
    return value.value if isinstance(value, TaskStatus) else str(value or TaskStatus.FAILED.value)


def _latest_control_tasks(db: Session) -> dict[str, ScraperTask]:
    latest: dict[str, ScraperTask] = {}
    rows = (
        db.query(ScraperTask)
        .filter(ScraperTask.task_type.in_(CONTROL_TASK_TYPES))
        .order_by(ScraperTask.id.desc())
        .all()
    )
    for task in rows:
        latest.setdefault(task.task_type, task)
    return latest


def _control_counts(db: Session) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    rows = (
        db.query(ScraperTask.task_type, ScraperTask.status, func.count(ScraperTask.id))
        .filter(ScraperTask.task_type.in_(CONTROL_TASK_TYPES))
        .group_by(ScraperTask.task_type, ScraperTask.status)
        .all()
    )
    for task_type, status, count in rows:
        counts[task_type][_status_value(status)] = int(count or 0)
    return counts


def _active_control_tasks(db: Session) -> dict[str, ScraperTask]:
    active: dict[str, ScraperTask] = {}
    rows = (
        db.query(ScraperTask)
        .filter(
            ScraperTask.task_type.in_(CONTROL_TASK_TYPES),
            ScraperTask.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]),
        )
        .order_by(ScraperTask.id.desc())
        .all()
    )
    for task in rows:
        active.setdefault(task.task_type, task)
    return active


def _state_fields(state: CollectorModuleState | None) -> dict[str, Any]:
    return {
        "interval_seconds": int(state.interval_seconds or 0) if state else 0,
        "enabled_at": state.enabled_at if state else None,
        "last_scheduled_at": state.last_scheduled_at if state else None,
        "next_run_at": state.next_run_at if state else None,
    }


def _persistent_module(
    task_type: str,
    latest: ScraperTask | None,
    active: ScraperTask | None,
    state: CollectorModuleState | None,
    counts: dict[str, int],
    pending_work: int,
) -> dict[str, Any]:
    enabled = bool(state.enabled) if state else bool(active)
    status = _status_value(active.status) if active else TaskStatus.RUNNING.value if enabled else "stopped"
    if active and active.progress_message:
        summary = active.progress_message
    elif enabled and state and state.last_error:
        summary = state.last_error
    elif enabled:
        summary = f"持续监听最新及正在直播的场次，当前待处理 {pending_work} 场"
    else:
        summary = "服务已彻底关闭，不会创建新任务"
    return {
        "key": TASK_TYPE_MODULES[task_type],
        "label": TASK_LABELS[task_type],
        "mode": "service",
        "enabled": enabled,
        "running": enabled,
        "status": status,
        "pending_count": pending_work,
        "processing_count": 1 if active and active.status == TaskStatus.RUNNING else 0,
        "completed_count": counts.get(TaskStatus.COMPLETED.value, 0),
        "failed_count": counts.get(TaskStatus.FAILED.value, 0),
        "summary": summary,
        "disabled_reason": state.last_error if state and state.last_error else "",
        **_state_fields(state),
    }


def _refresh_action(
    latest: ScraperTask | None,
    active: ScraperTask | None,
    counts: dict[str, int],
) -> dict[str, Any]:
    """把全场次补齐刷新展示为一次性动作，而不是长期服务开关。"""
    status = _status_value(active.status) if active else _status_value(latest.status) if latest else "idle"
    if active and active.progress_message:
        summary = active.progress_message
    elif latest and latest.status == TaskStatus.COMPLETED:
        summary = "上次补齐刷新已完成，可按需再次检查全部场次"
    elif latest and latest.status == TaskStatus.FAILED:
        summary = latest.error_message or "上次补齐刷新失败，可在任务队列重试"
    else:
        summary = "手动检查全部主播与全部场次，并补齐指标、评论、画像和流地址"
    return {
        "key": "data_refresh",
        "label": TASK_LABELS["collect_all"],
        "mode": "action",
        "enabled": False,
        "running": bool(active),
        "status": status,
        "pending_count": 1 if active and active.status == TaskStatus.PENDING else 0,
        "processing_count": 1 if active and active.status == TaskStatus.RUNNING else 0,
        "completed_count": counts.get(TaskStatus.COMPLETED.value, 0),
        "failed_count": counts.get(TaskStatus.FAILED.value, 0),
        "summary": summary,
        "disabled_reason": "",
        "interval_seconds": 0,
        "enabled_at": None,
        "last_scheduled_at": latest.created_at if latest else None,
        "next_run_at": None,
    }


def build_control_center(
    db: Session,
    asr_runtime: dict[str, Any],
    resource_usage: dict[str, Any],
) -> dict[str, Any]:
    """合并服务开关、待处理数量和统一任务进度。"""
    latest = _latest_control_tasks(db)
    active = _active_control_tasks(db)
    counts = _control_counts(db)
    states = collector_module_service.get_states(db)
    asr_plan = build_asr_resource_plan(resource_usage)

    asr_counts: dict[str, int] = defaultdict(int)
    for status, count in db.query(AsrTask.status, func.count(AsrTask.id)).group_by(AsrTask.status).all():
        asr_counts[_status_value(status)] = int(count or 0)

    modules = [
        _refresh_action(
            latest.get("collect_all"),
            active.get("collect_all"),
            counts.get("collect_all", {}),
        ),
        {
            "key": "monitor",
            "label": "直播监控",
            "mode": "service",
            "enabled": bool(states.get("monitor").enabled) if states.get("monitor") else scheduler_manager.running,
            "running": scheduler_manager.running,
            "status": (
                TaskStatus.RUNNING.value
                if scheduler_manager.running
                else "failed"
                if states.get("monitor") and states["monitor"].enabled
                else "stopped"
            ),
            "pending_count": 0,
            "processing_count": len(scheduler_manager.get_active_sessions()),
            "completed_count": 0,
            "failed_count": int(bool(scheduler_manager.last_error)),
            "summary": (
                "全部场次数据补齐刷新正在优先接管浏览器，监控保持开启并将在完成后自动恢复"
                if scheduler_manager.running and scheduler_manager.paused_for_collection
                else f"正在实时采集 {len(scheduler_manager.get_active_sessions())} 场直播"
                if scheduler_manager.running
                else "监控已开启，正在等待运行环境恢复"
                if states.get("monitor") and states["monitor"].enabled
                else "监控已彻底关闭，Chromium 可按需释放"
            ),
            "disabled_reason": scheduler_manager.last_error or (states.get("monitor").last_error if states.get("monitor") else "") or "",
            **_state_fields(states.get("monitor")),
        },
        {
            "key": "asr",
            "label": "ASR 话术转写",
            "mode": "service",
            "enabled": bool(states.get("asr").enabled) if states.get("asr") else bool(asr_runtime.get("enabled")),
            "running": bool(asr_runtime.get("enabled")),
            "status": (
                TaskStatus.RUNNING.value
                if asr_runtime.get("enabled")
                else "failed"
                if states.get("asr") and states["asr"].enabled
                else "stopped"
            ),
            "pending_count": asr_counts.get(TaskStatus.QUEUED.value, 0),
            "processing_count": asr_counts.get(TaskStatus.PROCESSING.value, 0),
            "completed_count": asr_counts.get(TaskStatus.COMPLETED.value, 0),
            "failed_count": asr_counts.get(TaskStatus.FAILED.value, 0),
            "summary": (
                f"{asr_plan.message}；转写中 {asr_counts.get(TaskStatus.PROCESSING.value, 0)} 场，"
                f"等待资源槽位 {asr_counts.get(TaskStatus.QUEUED.value, 0)} 场"
                if asr_runtime.get("enabled")
                else "ASR 已开启，正在等待模型与 Worker 恢复"
                if states.get("asr") and states["asr"].enabled
                else "ASR 已彻底关闭，模型内存已释放"
            ),
            "disabled_reason": (states.get("asr").last_error or "") if states.get("asr") else "",
            **_state_fields(states.get("asr")),
        },
        {
            **_persistent_module(
            "knowledge_sync",
            latest.get("knowledge_sync"),
            active.get("knowledge_sync"),
            states.get("knowledge"),
            counts.get("knowledge_sync", {}),
            pending_knowledge_session_count(db),
            ),
            "mode": "automatic",
            "enabled": True,
            "running": True,
        },
        {
            **_persistent_module(
            "dataease_sync",
            latest.get("dataease_sync"),
            active.get("dataease_sync"),
            states.get("dataease"),
            counts.get("dataease_sync", {}),
            pending_complete_session_count(db, force=False, include_live=True),
            ),
            "mode": "automatic",
            "enabled": True,
            "running": True,
        },
    ]

    tasks = list_unified_tasks(db, limit=100)
    active_tasks = [item for item in tasks if item["status"] in ACTIVE_STATUSES]
    running_tasks = [
        item
        for item in active_tasks
        if item["status"] in {TaskStatus.RUNNING.value, TaskStatus.PROCESSING.value}
    ]
    current_task = (running_tasks or active_tasks or [None])[0]
    return {
        "modules": modules,
        "current_task": current_task,
        "active_task_count": len(active_tasks),
        "queued_task_count": sum(
            item["status"] in {TaskStatus.PENDING.value, TaskStatus.QUEUED.value}
            for item in active_tasks
        ),
        "latest_task": tasks[0] if tasks else None,
        "resource_usage": resource_usage,
    }
