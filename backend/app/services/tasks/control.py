"""采集控制中心持久任务管理器。

一次性任务先写入 MySQL，再由后台循环按顺序执行。页面关闭不会丢任务；
用户停止时只设置取消标记，执行器在安全检查点退出，避免强杀浏览器或破坏事务。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logger import logger
from app.core.status import TaskStatus
from app.models.live_sessions import LiveSession
from app.models.scraper_accounts import ScraperAccount
from app.models.scraper_tasks import ScraperTask
from app.services.collector.browser import browser_manager
from app.services.collector.log_service import add_collector_log
from app.services.collector.scheduler import scheduler_manager
from app.services.tasks.batch_runners import (
    run_ai_review_batch,
    run_data_refresh,
    run_dataease_sync_batch,
    run_knowledge_sync_batch,
)
from app.services.tasks.exceptions import TaskBatchFailed, TaskCancellationRequested
from app.services.tasks.runtime import current_worker_id, ensure_task_identity, publish_task_event, touch_task


MODULE_TASK_TYPES = {
    "data_refresh": "collect_all",
    "ai_review": "ai_review",
    "knowledge": "knowledge_sync",
    "dataease": "dataease_sync",
}
TASK_TYPE_MODULES = {task_type: module for module, task_type in MODULE_TASK_TYPES.items()}
CONTROL_TASK_TYPES = tuple(TASK_TYPE_MODULES)
TASK_LABELS = {
    "collect_all": "全部场次数据补齐刷新",
    "ai_review": "AI 复盘",
    "knowledge_sync": "存入知识库",
    "dataease_sync": "DataEase 数据库同步",
}


def is_control_task(task: ScraperTask) -> bool:
    return task.task_type in CONTROL_TASK_TYPES


def is_cancel_requested(task_id: int) -> bool:
    """使用短会话读取取消标记，保证长任务能看见另一请求提交的变化。"""
    db = SessionLocal()
    try:
        task = db.get(ScraperTask, task_id)
        return bool(not task or task.cancel_requested_at or task.status == TaskStatus.CANCELLED)
    finally:
        db.close()


def _apply_progress_details(task: ScraperTask, details: dict[str, Any]) -> None:
    anchor_count = details.get("anchor_count", details.get("enterprise_anchor_count"))
    session_count = details.get(
        "discovered_session_count",
        details.get("enterprise_session_discovered_count"),
    )
    if anchor_count is not None:
        task.collected_anchor_count = max(0, int(anchor_count or 0))
    if session_count is not None:
        task.collected_session_count = max(0, int(session_count or 0))
    field_sources = {
        "new_session_count": ("session_count", "enterprise_session_synced_count"),
        "mapped_session_count": ("profile_count", "anchor_profile_synced_count"),
        "checked_detail_count": ("checked_count", "history_detail_checked_count"),
        "refreshed_detail_count": ("enriched_count", "history_detail_synced_count"),
        "failed_detail_count": ("failed_count", "history_detail_failed_count"),
        "remaining_detail_count": ("remaining_count", "history_detail_remaining_count"),
    }
    for task_field, source_keys in field_sources.items():
        value = next((details[key] for key in source_keys if details.get(key) is not None), None)
        if value is not None:
            setattr(task, task_field, max(0, int(value or 0)))


def _make_reporter(db: Session, task_id: int):
    """构造任务专属进度回调，统一保存进度和可读日志。"""

    def report(
        stage: str,
        percent: int,
        current: int,
        total: int,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        task = db.get(ScraperTask, task_id)
        if not task or task.cancel_requested_at or task.status == TaskStatus.CANCELLED:
            raise TaskCancellationRequested("用户已停止任务")
        details = details or {}
        previous_stage = task.progress_stage
        previous_percent = int(task.progress_percent or 0)
        task.progress_stage = stage[:50]
        task.progress_percent = max(0, min(99, int(percent or 0)))
        task.progress_current = max(0, int(current or 0))
        task.progress_total = max(0, int(total or 0))
        task.progress_message = str(message or "")[:500]
        _apply_progress_details(task, details)
        touch_task(task, current_worker_id("collector-control"))

        # 阶段变化、每增长 5% 或任务阶段结束时才写一条进度日志，避免长任务刷爆日志表。
        should_log = (
            previous_stage != stage
            or task.progress_percent >= previous_percent + 5
            or (task.progress_total and task.progress_current >= task.progress_total)
        )
        if should_log:
            session_id = details.get("session_id")
            session = db.get(LiveSession, int(session_id)) if session_id else None
            add_collector_log(
                db,
                task_id=task.id,
                session=session,
                room_id_str=str(details.get("room_id") or "") or None,
                level="info",
                stage=stage,
                event_type="progress",
                message=message,
                details={
                    "progress_percent": task.progress_percent,
                    "progress_current": task.progress_current,
                    "progress_total": task.progress_total,
                    **details,
                },
            )
        db.commit()
        publish_task_event(
            "scraper",
            task,
            "progress",
            {
                "stage": stage,
                "percent": task.progress_percent,
                "current": task.progress_current,
                "total": task.progress_total,
                "message": task.progress_message,
            },
        )

    return report


class CollectorTaskControlManager:
    """单队列执行资源较重的一次性任务，监控和 ASR 服务仍可独立运行。"""

    def __init__(self) -> None:
        self._loop_task: asyncio.Task | None = None
        self._active_task: asyncio.Task | None = None
        self._active_task_id: int | None = None
        self._stop_event = asyncio.Event()
        self._shutdown_requested = False

    @property
    def running(self) -> bool:
        return bool(self._loop_task and not self._loop_task.done())

    async def start(self) -> None:
        if self.running:
            return
        self._stop_event = asyncio.Event()
        self._shutdown_requested = False
        self._loop_task = asyncio.create_task(self._run_loop(), name="collector-control-loop")
        logger.info("采集控制中心任务循环已启动")

    async def stop(self) -> None:
        """停止取新任务，并等待当前线程在安全检查点退出后再关闭应用。"""
        self._stop_event.set()
        self._shutdown_requested = True
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            await asyncio.gather(self._loop_task, return_exceptions=True)
        if self._active_task and not self._active_task.done():
            logger.info("正在等待采集任务 #%s 从安全检查点退出", self._active_task_id)
            # asyncio.to_thread 创建的线程不能靠 cancel 真正停止。这里主动等待执行器
            # 看到 _shutdown_requested 后返回，避免后端已关闭但线程仍继续写数据库。
            await asyncio.gather(self._active_task, return_exceptions=True)
        self._active_task = None
        self._active_task_id = None
        self._loop_task = None
        logger.info("采集控制中心任务循环已停止")

    def recover_interrupted_tasks(self) -> int:
        """服务重启后恢复任务，并按当前“全部待处理场次”策略继续。"""
        db = SessionLocal()
        try:
            tasks = (
                db.query(ScraperTask)
                .filter(
                    ScraperTask.task_type.in_(CONTROL_TASK_TYPES),
                    ScraperTask.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]),
                )
                .all()
            )
            recovered_tasks = []
            for task in tasks:
                options = dict(task.task_options_json or {})
                options.setdefault("continuous", task.task_type != "collect_all")
                options.setdefault("latest_first", True)
                if task.task_type != "collect_all":
                    options["batch_size"] = settings.CONTINUOUS_TASK_BATCH_SIZE or None
                task.task_options_json = options
                if task.status == TaskStatus.RUNNING:
                    task.status = TaskStatus.PENDING
                    task.worker_id = None
                    task.heartbeat_at = None
                    task.cancel_requested_at = None
                    task.progress_stage = "recovered"
                    task.progress_message = "后端重启，任务已按全部待处理场次重新排队"
                    recovered_tasks.append(task)
            if tasks:
                db.commit()
                for task in recovered_tasks:
                    publish_task_event("scraper", task, "requeued", {"reason": "service_restart"})
            return len(recovered_tasks)
        finally:
            db.close()

    def _should_cancel(self, task_id: int) -> bool:
        """同时响应用户停止和应用安全关机，供各执行器在阶段间检查。"""
        return self._shutdown_requested or is_cancel_requested(task_id)

    def enqueue(self, module_key: str, options: dict[str, Any] | None = None) -> tuple[ScraperTask, bool]:
        task_type = MODULE_TASK_TYPES.get(module_key)
        if not task_type:
            raise ValueError("不支持的采集处理模块")
        db = SessionLocal()
        try:
            existing = (
                db.query(ScraperTask)
                .filter(
                    ScraperTask.task_type == task_type,
                    ScraperTask.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]),
                )
                .order_by(ScraperTask.id.desc())
                .first()
            )
            if existing:
                return existing, False

            account_id = None
            if task_type == "collect_all":
                account = (
                    db.query(ScraperAccount)
                    .filter(ScraperAccount.login_status == "logged_in")
                    .order_by(ScraperAccount.last_login_at.desc(), ScraperAccount.id.desc())
                    .first()
                )
                if not account or not account.cookie_saved:
                    raise ValueError("没有可用采集账号，请先扫码登录并检查 Cookie")
                account_id = account.id

            task = ScraperTask(
                account_id=account_id,
                task_type=task_type,
                status=TaskStatus.PENDING,
                task_options_json=options or {},
                progress_stage="queued",
                progress_message="任务已加入队列，等待执行",
                priority=0 if task_type == "collect_all" else 50,
            )
            ensure_task_identity(task, f"collector-control:{task_type}")
            db.add(task)
            db.commit()
            db.refresh(task)
            publish_task_event("scraper", task, "queued", {"module_key": module_key})
            return task, True
        finally:
            db.close()

    def request_cancel(self, task_id: int) -> ScraperTask:
        db = SessionLocal()
        try:
            task = db.get(ScraperTask, task_id)
            if not task or not is_control_task(task):
                raise ValueError("任务不存在或不支持停止")
            if task.status == TaskStatus.PENDING:
                task.status = TaskStatus.CANCELLED
                task.cancel_requested_at = datetime.utcnow()
                task.completed_at = datetime.utcnow()
                task.progress_stage = TaskStatus.CANCELLED
                task.progress_message = "任务已在执行前停止"
            elif task.status == TaskStatus.RUNNING:
                task.cancel_requested_at = datetime.utcnow()
                task.progress_stage = "stopping"
                task.progress_message = "正在等待当前安全检查点后停止"
            elif task.status != TaskStatus.CANCELLED:
                raise ValueError("只有排队中或运行中的任务可以停止")
            touch_task(task)
            db.commit()
            db.refresh(task)
            publish_task_event("scraper", task, "cancel_requested", {})
            return task
        finally:
            db.close()

    def request_cancel_task_type(self, task_type: str) -> list[ScraperTask]:
        """关闭长期模块时停止该模块全部排队和运行任务。"""
        if task_type not in CONTROL_TASK_TYPES:
            raise ValueError("任务类型不支持停止")
        db = SessionLocal()
        try:
            task_ids = [
                row[0]
                for row in db.query(ScraperTask.id)
                .filter(
                    ScraperTask.task_type == task_type,
                    ScraperTask.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]),
                )
                .all()
            ]
        finally:
            db.close()

        stopped = []
        for task_id in task_ids:
            stopped.append(self.request_cancel(task_id))
        return stopped

    def retry(self, task_id: int) -> ScraperTask:
        db = SessionLocal()
        try:
            original = db.get(ScraperTask, task_id)
            if not original or not is_control_task(original):
                raise ValueError("任务不存在或不支持重试")
            if original.status not in (TaskStatus.FAILED, TaskStatus.CANCELLED):
                raise ValueError("只有失败或已停止的任务可以重试")
            active = (
                db.query(ScraperTask)
                .filter(
                    ScraperTask.task_type == original.task_type,
                    ScraperTask.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]),
                )
                .first()
            )
            if active:
                raise ValueError(f"同类任务 #{active.id} 已在队列中")
            task = ScraperTask(
                account_id=original.account_id,
                task_type=original.task_type,
                status=TaskStatus.PENDING,
                task_options_json=original.task_options_json or {},
                retry_of_task_id=original.id,
                max_retries=original.max_retries,
                priority=original.priority,
                progress_stage="queued",
                progress_message=f"由任务 #{original.id} 重试，等待执行",
            )
            ensure_task_identity(task, f"collector-control:{original.task_type}:retry")
            db.add(task)
            db.commit()
            db.refresh(task)
            publish_task_event("scraper", task, "retried", {"retry_of_task_id": original.id})
            return task
        finally:
            db.close()

    def _next_pending_task_id(self) -> int | None:
        db = SessionLocal()
        try:
            row = (
                db.query(ScraperTask.id)
                .filter(
                    ScraperTask.task_type.in_(CONTROL_TASK_TYPES),
                    ScraperTask.status == TaskStatus.PENDING,
                )
                .order_by(ScraperTask.priority.asc(), ScraperTask.id.asc())
                .first()
            )
            return row[0] if row else None
        finally:
            db.close()

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                if self._active_task and self._active_task.done():
                    await asyncio.gather(self._active_task, return_exceptions=True)
                    self._active_task = None
                    self._active_task_id = None
                if not self._active_task:
                    task_id = self._next_pending_task_id()
                    if task_id:
                        self._active_task_id = task_id
                        self._active_task = asyncio.create_task(
                            self._execute(task_id),
                            name=f"collector-control-{task_id}",
                        )
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("采集控制中心循环异常: %s", exc)
                await asyncio.sleep(3)

    def _claim(self, task_id: int) -> str | None:
        db = SessionLocal()
        try:
            task = db.get(ScraperTask, task_id)
            if not task or task.status != TaskStatus.PENDING:
                return None
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.utcnow()
            task.completed_at = None
            task.error_message = None
            task.cancel_requested_at = None
            task.progress_stage = "starting"
            task.progress_message = "任务开始执行"
            task.retry_count = int(task.retry_count or 0) + 1
            touch_task(task, current_worker_id("collector-control"))
            db.commit()
            publish_task_event("scraper", task, "started", {"task_type": task.task_type})
            return task.task_type
        finally:
            db.close()

    async def _execute(self, task_id: int) -> None:
        task_type = self._claim(task_id)
        if not task_type:
            return
        try:
            if task_type == "collect_all":
                result = await self._run_data_refresh(task_id)
            else:
                result = await asyncio.to_thread(self._run_sync_batch, task_id, task_type)
            self._finish(task_id, TaskStatus.COMPLETED, result=result)
        except TaskCancellationRequested as exc:
            if self._shutdown_requested and not is_cancel_requested(task_id):
                self._requeue_after_shutdown(task_id)
            else:
                self._finish(task_id, TaskStatus.CANCELLED, error_message=str(exc))
        except TaskBatchFailed as exc:
            self._finish(task_id, TaskStatus.FAILED, result=exc.result, error_message=str(exc))
        except asyncio.CancelledError:
            self._requeue_after_shutdown(task_id)
            raise
        except Exception as exc:
            logger.exception("控制任务失败 task_id=%s type=%s: %s", task_id, task_type, exc)
            self._finish(task_id, TaskStatus.FAILED, error_message=str(exc)[:1000])

    async def _run_data_refresh(self, task_id: int) -> dict[str, Any]:
        db = SessionLocal()
        try:
            report = _make_reporter(db, task_id)
            # 点击补齐刷新后先阻止监控接新页面，再等待当前页面安全结束。刷新在共享
            # 会话协调器中拥有优先权，两个服务不会同时碰同一份 Cookie 和 Context。
            scheduler_manager.begin_collection_takeover()
            report("browser_takeover", 1, 0, 0, "正在等待实时监控交出浏览器登录会话")
            async with browser_manager.session_lease(
                f"data-refresh:{task_id}",
                kind="refresh",
            ):
                report("browser_takeover", 2, 0, 0, "已接管浏览器，实时监控将在刷新结束后自动恢复")
                return await run_data_refresh(
                    db,
                    task_id,
                    report,
                    lambda: self._should_cancel(task_id),
                )
        finally:
            scheduler_manager.resume_after_collection()
            db.close()

    def _run_sync_batch(self, task_id: int, task_type: str) -> dict[str, Any]:
        db = SessionLocal()
        try:
            task = db.get(ScraperTask, task_id)
            options = task.task_options_json if task and isinstance(task.task_options_json, dict) else {}
            batch_size = options.get("batch_size")
            if batch_size is not None:
                parsed_batch_size = int(batch_size)
                batch_size = max(1, parsed_batch_size) if parsed_batch_size > 0 else None
            report = _make_reporter(db, task_id)
            runner = {
                "ai_review": run_ai_review_batch,
                "knowledge_sync": run_knowledge_sync_batch,
                "dataease_sync": run_dataease_sync_batch,
            }.get(task_type)
            if not runner:
                raise RuntimeError(f"未注册任务执行器: {task_type}")
            return runner(
                db,
                task_id,
                report,
                lambda: self._should_cancel(task_id),
                batch_size=batch_size,
            )
        finally:
            db.close()

    def _finish(
        self,
        task_id: int,
        status: str,
        *,
        result: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        db = SessionLocal()
        try:
            task = db.get(ScraperTask, task_id)
            if not task:
                return
            task.status = status
            task.completed_at = datetime.utcnow()
            task.result_json = result or task.result_json
            task.error_message = error_message[:1000] if error_message else None
            task.progress_stage = status
            task.progress_message = (
                "任务已完成"
                if status == TaskStatus.COMPLETED
                else "任务已按用户要求安全停止"
                if status == TaskStatus.CANCELLED
                else error_message or "任务执行失败"
            )[:500]
            if status == TaskStatus.COMPLETED:
                task.progress_percent = 100
                if not task.progress_total:
                    task.progress_total = task.progress_current
            touch_task(task)
            add_collector_log(
                db,
                task_id=task.id,
                level="info" if status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED) else "error",
                stage=status,
                event_type=f"task_{status}",
                message=f"{TASK_LABELS.get(task.task_type, task.task_type)}{task.progress_message}",
                details=result or {"error": task.error_message},
            )
            db.commit()
            publish_task_event("scraper", task, status, result or {"error": task.error_message or ""})
        finally:
            db.close()

    def _requeue_after_shutdown(self, task_id: int) -> None:
        db = SessionLocal()
        try:
            task = db.get(ScraperTask, task_id)
            if task and task.status == TaskStatus.RUNNING:
                task.status = TaskStatus.PENDING
                task.worker_id = None
                task.heartbeat_at = None
                task.completed_at = None
                task.progress_stage = "recovered"
                task.progress_message = "服务正在重启，任务稍后重新执行"
                db.commit()
        finally:
            db.close()


collector_task_control = CollectorTaskControlManager()
