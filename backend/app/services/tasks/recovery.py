"""回收已经失去执行进程的实时采集任务。"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.status import TaskStatus
from app.models.scraper_tasks import ScraperTask


MONITOR_RUNTIME_TASK_TYPES = (
    "live_detail",
    "stream_refresh",
    "metrics",
    "comments",
    "profiles",
)


def _worker_process_id(worker_id: str | None) -> int | None:
    """从 ``类型:主机名:PID`` 格式中安全解析执行进程编号。"""
    if not worker_id:
        return None
    try:
        return int(worker_id.rsplit(":", 1)[-1])
    except (TypeError, ValueError):
        return None


def recover_orphaned_monitor_tasks(
    db: Session,
    *,
    current_pid: int | None = None,
    stale_after_seconds: int = 120,
) -> list[ScraperTask]:
    """把旧后端遗留且已失去心跳的实时任务标记为中断。

    这里只处理 Worker PID 与当前进程不同的任务，避免把当前正在读取大屏的
    慢请求误判为失败；实时监控下一轮会依据直播状态自动创建新的采集任务。
    """
    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=max(30, stale_after_seconds))
    process_id = current_pid if current_pid is not None else os.getpid()
    candidates = (
        db.query(ScraperTask)
        .filter(
            ScraperTask.status == TaskStatus.RUNNING,
            ScraperTask.task_type.in_(MONITOR_RUNTIME_TASK_TYPES),
            or_(
                ScraperTask.heartbeat_at < cutoff,
                and_(ScraperTask.heartbeat_at.is_(None), ScraperTask.started_at < cutoff),
            ),
        )
        .all()
    )

    recovered = []
    for task in candidates:
        worker_pid = _worker_process_id(task.worker_id)
        if worker_pid == process_id:
            continue
        task.status = TaskStatus.FAILED
        task.completed_at = now
        task.error_message = "执行该任务的后端进程已退出，实时监控将在下一轮自动恢复"
        task.progress_stage = "interrupted"
        task.progress_message = "旧进程任务已回收"
        task.worker_id = None
        task.heartbeat_at = now
        recovered.append(task)

    if recovered:
        db.commit()
    return recovered
