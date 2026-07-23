"""数据采集动作、长期服务开关与后台自动同步调度。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logger import logger
from app.core.status import TaskStatus
from app.models.asr_audio_chunks import AsrAudioChunk
from app.models.asr_tasks import AsrTask
from app.models.collector_module_states import CollectorModuleState
from app.models.scraper_accounts import ScraperAccount
from app.models.scraper_tasks import ScraperTask
from app.services.asr.control import start_asr_runtime, stop_asr_runtime
from app.services.asr.queue import queue_auto_transcriptions
from app.services.collector.browser import browser_manager
from app.services.collector.scheduler import scheduler_manager
from app.services.resources.system_usage import get_system_usage
from app.services.resources.asr_policy import build_asr_resource_plan
from app.services.sync.de_sync import pending_complete_session_count
from app.services.tasks.batch_runners import pending_knowledge_session_count
from app.services.tasks.control import MODULE_TASK_TYPES, collector_task_control


MODULE_KEYS = ("data_refresh", "monitor", "asr", "knowledge", "dataease")
SCHEDULED_SERVICE_MODULE_KEYS = ("knowledge", "dataease")
AUTOMATIC_MODULE_KEYS = ("knowledge", "dataease")


def _module_intervals() -> dict[str, int]:
    return {
        "data_refresh": settings.DATA_REFRESH_INTERVAL_SECONDS,
        "monitor": settings.MONITOR_CHECK_INTERVAL,
        "asr": 5,
        "ai_review": settings.AI_REVIEW_INTERVAL_SECONDS,
        "knowledge": settings.KNOWLEDGE_SYNC_INTERVAL_SECONDS,
        "dataease": settings.DATAEASE_SYNC_INTERVAL_SECONDS,
    }


def _active_task_types() -> set[str]:
    db = SessionLocal()
    try:
        return {
            row[0]
            for row in db.query(ScraperTask.task_type)
            .filter(
                ScraperTask.task_type.in_(tuple(MODULE_TASK_TYPES.values())),
                ScraperTask.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]),
            )
            .distinct()
            .all()
        }
    finally:
        db.close()


class CollectorModuleServiceManager:
    """管理手动补齐刷新、长期服务开关和知识库自动入库。"""

    def __init__(self) -> None:
        self._loop_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    @property
    def running(self) -> bool:
        return bool(self._loop_task and not self._loop_task.done())

    def ensure_states(self) -> None:
        """建立控制状态；知识库固定后台运行，刷新固定为手动动作。"""
        active_types = _active_task_types()
        intervals = _module_intervals()
        db = SessionLocal()
        try:
            existing = {
                state.module_key: state
                for state in db.query(CollectorModuleState)
                .filter(CollectorModuleState.module_key.in_(MODULE_KEYS))
                .all()
            }
            now = datetime.utcnow()
            for module_key in MODULE_KEYS:
                state = existing.get(module_key)
                if state:
                    state.interval_seconds = max(5, int(intervals[module_key]))
                    if module_key == "data_refresh":
                        state.enabled = False
                        state.next_run_at = None
                    elif module_key in AUTOMATIC_MODULE_KEYS:
                        state.enabled = True
                        state.disabled_at = None
                        state.enabled_at = state.enabled_at or now
                        state.next_run_at = state.next_run_at or now
                    continue
                task_type = MODULE_TASK_TYPES.get(module_key)
                enabled = (
                    settings.MONITOR_ENABLED
                    if module_key == "monitor"
                    else settings.ASR_AUTO_START
                    if module_key == "asr"
                    else True
                    if module_key in AUTOMATIC_MODULE_KEYS
                    else False
                    if module_key == "data_refresh"
                    else bool(task_type and task_type in active_types)
                )
                db.add(
                    CollectorModuleState(
                        module_key=module_key,
                        enabled=enabled,
                        interval_seconds=max(5, int(intervals[module_key])),
                        enabled_at=now if enabled else None,
                        disabled_at=None if enabled else now,
                        next_run_at=now if enabled else None,
                    )
                )
            # AI 复盘改由场次详情页手动生成，旧版本留下的自动开关必须停用。
            legacy_ai_state = db.get(CollectorModuleState, "ai_review")
            if legacy_ai_state:
                legacy_ai_state.enabled = False
                legacy_ai_state.next_run_at = None
                legacy_ai_state.disabled_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()

    async def start(self) -> None:
        if self.running:
            return
        self.ensure_states()
        await asyncio.to_thread(collector_task_control.request_cancel_task_type, "ai_review")
        await self._restore_runtime_services()
        self._stop_event = asyncio.Event()
        self._loop_task = asyncio.create_task(self._run_loop(), name="collector-module-service-loop")
        logger.info("数据采集服务与知识库自动入库调度器已启动")

    async def shutdown(self) -> None:
        """应用退出时释放运行资源，但不改变用户保存的开关状态。"""
        await self.stop_scheduling()
        await self.release_runtime_resources()

    async def stop_scheduling(self) -> None:
        """先停止创建新批次，供应用按安全顺序结束在途任务。"""
        self._stop_event.set()
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            await asyncio.gather(self._loop_task, return_exceptions=True)
        self._loop_task = None

    async def release_runtime_resources(self) -> None:
        """在控制任务停止后关闭监控、ASR 和浏览器进程。"""
        if scheduler_manager.running:
            await scheduler_manager.stop()
        await asyncio.to_thread(stop_asr_runtime)
        await browser_manager.close()
        logger.info("数据采集控制中心运行资源已释放")

    def get_states(self, db) -> dict[str, CollectorModuleState]:
        return {
            state.module_key: state
            for state in db.query(CollectorModuleState)
            .filter(CollectorModuleState.module_key.in_(MODULE_KEYS))
            .all()
        }

    def is_enabled(self, module_key: str) -> bool:
        db = SessionLocal()
        try:
            state = db.get(CollectorModuleState, module_key)
            return bool(state and state.enabled)
        finally:
            db.close()

    async def enable(self, module_key: str) -> tuple[ScraperTask | None, str]:
        if module_key not in MODULE_KEYS:
            raise ValueError("采集处理模块不存在")
        if module_key == "data_refresh" and not self._has_available_account():
            raise ValueError("没有可用采集账号，请先扫码登录并检查 Cookie")

        if module_key == "data_refresh":
            task, created = collector_task_control.enqueue(
                module_key,
                options={
                    "continuous": False,
                    "latest_first": True,
                    "scope": "all_sessions",
                    "requested_at": datetime.utcnow().isoformat(),
                },
            )
            message = (
                f"全部场次数据补齐刷新任务 #{task.id} 已优先排队，刷新期间将接管实时监控浏览器"
                if created
                else f"全部场次数据补齐刷新任务 #{task.id} 已在运行或排队，请勿重复提交"
            )
            return task, message
        if module_key in AUTOMATIC_MODULE_KEYS:
            self._set_enabled(module_key, True)
            label = "知识库入库" if module_key == "knowledge" else "DataEase 只读宽表同步"
            return None, f"{label}为后台自动服务，无需手动开启"

        if module_key == "monitor":
            await scheduler_manager.start()
        elif module_key == "asr":
            await asyncio.to_thread(start_asr_runtime)

        self._set_enabled(module_key, True)
        if module_key == "asr":
            db = SessionLocal()
            try:
                plan = build_asr_resource_plan(get_system_usage(force=True))
                queued = queue_auto_transcriptions(
                    db,
                    limit=plan.queue_capacity,
                    queue_capacity=plan.queue_capacity,
                )
            finally:
                db.close()
            return None, f"ASR 持续转写已开启；{plan.message}，当前处理槽位 {queued['active_count']} 场"
        if module_key == "monitor":
            return None, "直播监控已开启，将持续发现并采集正在开播的场次"

        task = await asyncio.to_thread(self._schedule_module_now_sync, module_key, False)
        if task:
            return task, f"{module_key} 持续服务已开启，最新数据任务 #{task.id} 已进入队列"
        state_error = self._state_error(module_key)
        if state_error:
            return None, f"持续服务已开启；{state_error}"
        return None, "持续服务已开启，当前没有待处理数据，将自动监听最新场次"

    async def disable(self, module_key: str) -> tuple[int, str]:
        if module_key not in MODULE_KEYS:
            raise ValueError("采集处理模块不存在")
        if module_key == "data_refresh":
            stopped_count = len(collector_task_control.request_cancel_task_type("collect_all"))
            return stopped_count, f"已请求停止全部场次数据补齐刷新，共 {stopped_count} 个任务"
        if module_key in AUTOMATIC_MODULE_KEYS:
            label = "知识库入库" if module_key == "knowledge" else "DataEase 只读宽表同步"
            raise ValueError(f"{label}为后台基础服务，已改为自动执行，不能关闭")
        self._set_enabled(module_key, False)
        stopped_count = 0

        task_type = MODULE_TASK_TYPES.get(module_key)
        if task_type:
            stopped_count = len(collector_task_control.request_cancel_task_type(task_type))
        elif module_key == "monitor":
            await scheduler_manager.stop()
        elif module_key == "asr":
            stopped_count = await asyncio.to_thread(self._cancel_asr_tasks_sync)
            await asyncio.to_thread(stop_asr_runtime)

        if module_key in {"data_refresh", "monitor"}:
            await self._release_browser_if_unused()
        return stopped_count, self._disabled_message(module_key, stopped_count)

    def _set_enabled(self, module_key: str, enabled: bool) -> None:
        db = SessionLocal()
        try:
            state = db.get(CollectorModuleState, module_key)
            if not state:
                state = CollectorModuleState(
                    module_key=module_key,
                    interval_seconds=max(5, _module_intervals()[module_key]),
                )
                db.add(state)
            now = datetime.utcnow()
            state.enabled = enabled
            state.last_error = None
            if enabled:
                state.enabled_at = now
                state.disabled_at = None
                state.next_run_at = now
            else:
                state.disabled_at = now
                state.next_run_at = None
            db.commit()
        finally:
            db.close()

    async def _restore_runtime_services(self) -> None:
        db = SessionLocal()
        try:
            states = self.get_states(db)
            monitor_enabled = bool(states.get("monitor") and states["monitor"].enabled)
            asr_enabled = bool(states.get("asr") and states["asr"].enabled)
        finally:
            db.close()
        if monitor_enabled:
            await scheduler_manager.start()
        if asr_enabled:
            try:
                await asyncio.to_thread(start_asr_runtime)
            except Exception as exc:
                self._save_error("asr", f"ASR 恢复失败：{str(exc)[:400]}")
                logger.warning("ASR 持续服务恢复失败: %s", exc)

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                usage = await asyncio.to_thread(get_system_usage)
                await asyncio.to_thread(self._schedule_due_modules_sync, usage)
                await self._release_browser_if_unused()
                await asyncio.sleep(max(5, settings.COLLECTOR_SERVICE_TICK_SECONDS))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("持续模块调度异常: %s", exc)
                await asyncio.sleep(max(5, settings.COLLECTOR_SERVICE_TICK_SECONDS))

    def _schedule_due_modules_sync(self, usage: dict[str, Any]) -> None:
        db = SessionLocal()
        try:
            now = datetime.utcnow()
            states = (
                db.query(CollectorModuleState)
                .filter(
                    CollectorModuleState.module_key.in_(SCHEDULED_SERVICE_MODULE_KEYS),
                    CollectorModuleState.enabled.is_(True),
                )
                .order_by(CollectorModuleState.module_key.asc())
                .all()
            )
            for state in states:
                if state.next_run_at and state.next_run_at > now:
                    continue
                if usage.get("pressure_level") in {"high", "critical"}:
                    delay = max(30, state.interval_seconds * settings.RESOURCE_BACKOFF_MULTIPLIER)
                    state.next_run_at = now + timedelta(seconds=delay)
                    state.last_error = str(usage.get("pressure_message") or "电脑资源压力较高")[:500]
                    continue
                state.last_error = None
                self._schedule_state(db, state, now)
            db.commit()
        finally:
            db.close()

    def _schedule_module_now_sync(self, module_key: str, ignore_resource_pressure: bool) -> ScraperTask | None:
        usage = get_system_usage()
        db = SessionLocal()
        try:
            state = db.get(CollectorModuleState, module_key)
            if not state or not state.enabled:
                return None
            if not ignore_resource_pressure and usage.get("pressure_level") in {"high", "critical"}:
                delay = max(30, state.interval_seconds * settings.RESOURCE_BACKOFF_MULTIPLIER)
                state.next_run_at = datetime.utcnow() + timedelta(seconds=delay)
                state.last_error = str(usage.get("pressure_message") or "电脑资源压力较高")[:500]
                db.commit()
                return None
            task = self._schedule_state(db, state, datetime.utcnow())
            db.commit()
            return task
        finally:
            db.close()

    def _schedule_state(
        self,
        db,
        state: CollectorModuleState,
        now: datetime,
    ) -> ScraperTask | None:
        task_type = MODULE_TASK_TYPES[state.module_key]
        active = (
            db.query(ScraperTask.id)
            .filter(
                ScraperTask.task_type == task_type,
                ScraperTask.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]),
            )
            .first()
        )
        if active:
            return None

        pending_count = self._pending_count(db, state.module_key)
        state.next_run_at = now + timedelta(seconds=max(5, state.interval_seconds))
        if state.module_key != "data_refresh" and pending_count == 0:
            return None

        options = {
            "continuous": True,
            "latest_first": True,
            "batch_size": settings.CONTINUOUS_TASK_BATCH_SIZE or None,
            "scheduled_at": now.isoformat(),
        }
        task, _created = collector_task_control.enqueue(state.module_key, options=options)
        state.last_scheduled_at = now
        state.last_task_id = task.id
        return task

    @staticmethod
    def _pending_count(db, module_key: str) -> int:
        if module_key == "knowledge":
            return pending_knowledge_session_count(db)
        if module_key == "dataease":
            return pending_complete_session_count(db, force=False, include_live=True)
        return 1

    @staticmethod
    def _has_available_account() -> bool:
        db = SessionLocal()
        try:
            count = db.query(func.count(ScraperAccount.id)).filter(
                ScraperAccount.login_status == "logged_in",
                ScraperAccount.storage_state_path.isnot(None),
            ).scalar()
            return int(count or 0) > 0
        finally:
            db.close()

    @staticmethod
    def _cancel_asr_tasks_sync() -> int:
        db = SessionLocal()
        try:
            tasks = db.query(AsrTask).filter(
                AsrTask.status.in_([TaskStatus.QUEUED, TaskStatus.PROCESSING])
            ).all()
            task_ids = [task.id for task in tasks]
            if task_ids:
                db.query(AsrAudioChunk).filter(
                    AsrAudioChunk.task_id.in_(task_ids),
                    AsrAudioChunk.status == TaskStatus.PROCESSING,
                ).update(
                    {
                        AsrAudioChunk.status: TaskStatus.PENDING,
                        AsrAudioChunk.completed_at: None,
                        AsrAudioChunk.worker_id: None,
                        AsrAudioChunk.error_message: "ASR 开关已关闭，保留分片等待重新开启",
                    },
                    synchronize_session=False,
                )
            now = datetime.utcnow()
            for task in tasks:
                task.status = TaskStatus.CANCELLED
                task.cancel_requested_at = now
                task.completed_at = now
                task.worker_id = None
                task.heartbeat_at = now
                task.error_message = "ASR 开关已关闭，任务已暂停并释放模型资源"
            db.commit()
            return len(tasks)
        finally:
            db.close()

    async def _release_browser_if_unused(self) -> None:
        db = SessionLocal()
        try:
            states = self.get_states(db)
            browser_service_enabled = bool(states.get("monitor") and states["monitor"].enabled)
            active_refresh = db.query(ScraperTask.id).filter(
                ScraperTask.task_type == "collect_all",
                ScraperTask.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]),
            ).first()
        finally:
            db.close()
        if browser_service_enabled or active_refresh:
            return
        if await scheduler_manager.wait_until_idle(timeout_seconds=5):
            await browser_manager.close()

    def _save_error(self, module_key: str, message: str) -> None:
        db = SessionLocal()
        try:
            state = db.get(CollectorModuleState, module_key)
            if state:
                state.last_error = message[:500]
                db.commit()
        finally:
            db.close()

    @staticmethod
    def _state_error(module_key: str) -> str:
        db = SessionLocal()
        try:
            state = db.get(CollectorModuleState, module_key)
            return str(state.last_error or "") if state else ""
        finally:
            db.close()

    @staticmethod
    def _disabled_message(module_key: str, stopped_count: int) -> str:
        resources = {
            "monitor": "直播监控已关闭；没有补齐刷新任务时 Chromium 会自动退出",
            "asr": "ASR 已关闭，Worker 与 FunASR 模型容器已停止",
        }
        suffix = f"，已停止 {stopped_count} 个任务" if stopped_count else ""
        return f"{resources[module_key]}{suffix}"


collector_module_service = CollectorModuleServiceManager()
