"""
ASR Worker 进程 — 独立运行的话术转写服务

从 DB 轮询 asr_tasks，通过 ffmpeg pipe 拉流 → FunASR 识别 → 写入 transcript_segments

启动:
    cd backend && source .venv/bin/activate
    python -m workers.asr_worker

环境变量:
    ASR_WORKER_MODE=true
    ASR_DYNAMIC_MAX_TASKS=4
"""
import asyncio
import hashlib
import signal
from time import monotonic
from datetime import datetime, timedelta

import httpx
from sqlalchemy.exc import DataError

from app.core.config import settings
from app.core.logger import logger
from app.core.database import SessionLocal
from app.core.status import TaskStatus
from app.core.security import build_internal_worker_token
from app.models.asr_tasks import AsrTask
from app.models.asr_audio_chunks import AsrAudioChunk
from app.models.transcript_segments import TranscriptSegment
from app.models.transcript_full_texts import TranscriptFullText
from app.models.stream_sources import StreamSource
from app.models.live_sessions import LiveSession
from app.models.scraper_logs import ScraperLog
from app.services.asr.chunks import (
    build_chunk_ranges,
    next_live_chunk_range,
    reconcile_existing_chunks,
)
from app.services.asr.m3u8_pipe import M3u8Pipe, sanitize_ffmpeg_error
from app.services.asr.funasr_client import FunasrClient
from app.services.asr.queue import (
    list_queued_task_ids_latest_first,
    queue_auto_transcriptions,
    queue_session_transcription,
    recover_interrupted_chunk,
    requeue_offline_task_for_live_priority,
)
from app.services.asr.websocket_manager import ws_manager
from app.services.asr.corrector import correct_text as correct_asr_text
from app.services.ai.post_collection import process_session_post_collection
from app.services.collector.stream_health import probe_stream_url
from app.services.resources.asr_policy import AsrResourcePlan, build_asr_resource_plan
from app.services.resources.system_usage import get_system_usage
from app.services.tasks.runtime import (
    current_worker_id,
    ensure_task_identity,
    publish_task_event,
    touch_task,
)
from app.services.tasks.exceptions import TaskCancellationRequested

# ASR Worker 调用后端 API 的基地址（同机部署）
_BACKEND_BASE_URL = "http://localhost:8000/api/v1"


class _YieldToLiveTask(Exception):
    """离线任务在安全点主动礼让实时直播，不属于失败或人工取消。"""


def is_full_text_too_long_error(exc: DataError) -> bool:
    """识别迁移前 MySQL TEXT 容量不足错误。"""
    return bool(getattr(exc, "orig", None) and getattr(exc.orig, "args", ()) and exc.orig.args[0] == 1406)


def segment_type_for_task(task_type: str) -> str:
    """离线终稿完成前先写入隐藏暂存类型，实时初稿则立即可见。"""
    return "asr_offline_pending" if task_type == "offline" else "asr_realtime"


def should_handoff_realtime_task(task_type: str, live_status: str) -> bool:
    """实时任务被领取时若已经下播，就交给新离线任务而不是篡改任务类型。"""
    return task_type == "realtime" and live_status != "live"


def postprocess_status_for_task(task_type: str) -> str:
    """直播初稿不生成最终复盘，只有下播终稿进入 AI 后处理。"""
    return TaskStatus.PENDING if task_type == "offline" else "skipped"


def build_chunk_failure_message(error: Exception, pipe: M3u8Pipe | None = None) -> str:
    """生成保存到任务抽屉里的分片失败原因。

    ffmpeg 的 404/403/过期等底层取流错误以前只写在日志里，数据库只保存
    “真实流未输出任何音频帧”，运营看到失败任务时不知道该刷新流地址还是重启
    FunASR。这里把最近一次 ffmpeg stderr 拼进去，同时截断长度，避免错误信息过长。
    """
    message = str(error)
    ffmpeg_error = (getattr(pipe, "last_error_message", "") or "").strip()
    if "未输出任何音频帧" in message and ffmpeg_error:
        message = f"{message}；ffmpeg 错误：{ffmpeg_error}"
    return message[:500]


class AsrWorker:
    """ASR 转写 Worker"""

    # FunASR Docker 容器名（与 docker-compose.yml 中 container_name 保持一致）
    _FUNASR_CONTAINER = "douyin_live_funasr"
    # 从根目录 .env 读取等待上限。真实 8GB Mac 上容器崩溃后重新校验
    # 1.6GB 模型可能超过 5 分钟，不能再使用写死的短超时。
    _FUNASR_CONNECT_TIMEOUT = settings.ASR_ENGINE_READY_TIMEOUT_SECONDS

    def __init__(self):
        self._semaphore = asyncio.Semaphore(max(1, settings.ASR_DYNAMIC_MAX_TASKS))
        self._active_tasks: set[asyncio.Task] = set()
        self._active_task_ids: set[int] = set()
        self._active_chunk_task_ids: set[int] = set()
        self._resource_slot_lock = asyncio.Lock()
        # 当前 FunASR C++ 容器实测只能稳定处理一条 WebSocket。
        # 即使资源策略允许并行准备任务，也必须在这里串行进入模型连接。
        self._funasr_connection_lock = asyncio.Lock()
        self._last_resource_message = ""
        self._active_postprocess_tasks: set[asyncio.Task] = set()
        self._active_postprocess_ids: set[int] = set()
        self._running = False
        self._poll_interval = 5  # 秒
        self._worker_id = current_worker_id("asr")

    async def run(self):
        """主循环"""
        self._running = True
        logger.info("ASR Worker 启动（资源自适应并发，安全上限: %s）", settings.ASR_DYNAMIC_MAX_TASKS)
        self._recover_stale_tasks(recover_all=True)

        while self._running:
            try:
                await self._poll_tasks()
                # AI 复盘由详情页手动生成，知识库和 DataEase 由后台自动同步。
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"ASR Worker 异常: {e}")
                await asyncio.sleep(10)

    def _recover_stale_tasks(self, recover_all: bool = False):
        """回收重启遗留或心跳超时的任务，并保留已完成分片。"""
        db = SessionLocal()
        try:
            query = db.query(AsrTask).filter(AsrTask.status == "processing")
            if not recover_all:
                cutoff = datetime.utcnow() - timedelta(seconds=max(60, settings.TASK_HEARTBEAT_TIMEOUT_SECONDS))
                query = query.filter(AsrTask.heartbeat_at < cutoff)
                if self._active_task_ids:
                    query = query.filter(~AsrTask.id.in_(self._active_task_ids))
            stale = query.all()
            for task in stale:
                # Worker 退出属于基础设施中断，不是直播内容识别失败，因此退还本次
                # 任务级尝试次数，并始终从已完成分片之后继续。
                task.retry_count = max(0, int(task.retry_count or 0) - 1)
                task.status = TaskStatus.QUEUED
                task.error_message = "Worker 中断，已保留完成分片并从断点继续"
                task.completed_at = None
                task.worker_id = None
                touch_task(task)
                chunks = db.query(AsrAudioChunk).filter(
                    AsrAudioChunk.task_id == task.id,
                    AsrAudioChunk.status == "processing",
                ).all()
                for chunk in chunks:
                    recover_interrupted_chunk(chunk)
            if stale:
                db.commit()
                for task in stale:
                    publish_task_event("asr", task, "recovered", {"status": task.status})
                logger.warning("Worker 从断点回收 %s 个遗留 ASR 任务", len(stale))

            postprocess_query = db.query(AsrTask).filter(AsrTask.postprocess_status == "processing")
            if not recover_all:
                cutoff = datetime.utcnow() - timedelta(seconds=max(60, settings.TASK_HEARTBEAT_TIMEOUT_SECONDS))
                postprocess_query = postprocess_query.filter(AsrTask.postprocess_started_at < cutoff)
                if self._active_postprocess_ids:
                    postprocess_query = postprocess_query.filter(~AsrTask.id.in_(self._active_postprocess_ids))
            stale_postprocess = postprocess_query.all()
            for task in stale_postprocess:
                task.postprocess_status = (
                    "pending" if (task.postprocess_attempt_count or 0) < (task.max_retries or 3) else "failed"
                )
                task.postprocess_error = "Worker 重启，采集后处理将从幂等阶段继续"
                task.postprocess_started_at = None
            if stale_postprocess:
                db.commit()
                logger.warning("Worker 从断点回收 %s 个采集后处理任务", len(stale_postprocess))
        finally:
            db.close()

    async def _poll_tasks(self):
        """轮询 queued 任务"""
        # Worker 未重启但协程被中断时，也要自动回收数据库中的旧执行状态。
        self._recover_stale_tasks()
        plan = await asyncio.to_thread(self._current_resource_plan)
        if plan.message != self._last_resource_message:
            logger.info(plan.message)
            self._last_resource_message = plan.message
        available_slots = max(0, plan.target_concurrency - len(self._active_tasks))

        db = SessionLocal()
        try:
            # 即使单槽位正在跑离线任务，也要先发现并排队正在直播的场次。
            # 离线任务只有看见 queued 直播任务，才能在当前两分钟分片结束后礼让。
            queue_auto_transcriptions(
                db,
                limit=plan.queue_capacity,
                queue_capacity=plan.queue_capacity,
            )
            if available_slots == 0:
                return
            queued_ids = list_queued_task_ids_latest_first(
                db,
                min(plan.queue_capacity, available_slots),
            )

            for task_id in queued_ids:
                now = datetime.utcnow()
                claimed = db.query(AsrTask).filter(
                    AsrTask.id == task_id,
                    AsrTask.status == "queued",
                    AsrTask.cancel_requested_at.is_(None),
                ).update(
                    {
                        AsrTask.status: "processing",
                        AsrTask.started_at: now,
                        AsrTask.completed_at: None,
                        AsrTask.error_message: None,
                        AsrTask.worker_id: self._worker_id,
                        AsrTask.heartbeat_at: now,
                        AsrTask.retry_count: AsrTask.retry_count + 1,
                    },
                    synchronize_session=False,
                )
                db.commit()
                if not claimed:
                    continue
                worker_task = asyncio.create_task(self._process_task(task_id))
                self._active_tasks.add(worker_task)
                self._active_task_ids.add(task_id)

                def discard_finished(done_task, claimed_task_id=task_id):
                    self._active_tasks.discard(done_task)
                    self._active_task_ids.discard(claimed_task_id)

                worker_task.add_done_callback(discard_finished)
        finally:
            db.close()

    async def _poll_postprocess_tasks(self):
        """单并发执行话术评分、AI复盘和知识库同步，避免挤占本机资源。"""
        if self._active_postprocess_tasks:
            return
        db = SessionLocal()
        try:
            row = (
                db.query(AsrTask)
                .filter(
                    AsrTask.status == "completed",
                    AsrTask.task_type == "offline",
                    AsrTask.postprocess_status.in_(["pending", "failed"]),
                    AsrTask.postprocess_attempt_count < AsrTask.max_retries,
                )
                .order_by(AsrTask.completed_at.asc(), AsrTask.id.asc())
                .first()
            )
            if not row:
                return
            now = datetime.utcnow()
            claimed = db.query(AsrTask).filter(
                AsrTask.id == row.id,
                AsrTask.postprocess_status.in_(["pending", "failed"]),
            ).update(
                {
                    AsrTask.postprocess_status: "processing",
                    AsrTask.postprocess_started_at: now,
                    AsrTask.postprocess_completed_at: None,
                    AsrTask.postprocess_error: None,
                    AsrTask.postprocess_attempt_count: AsrTask.postprocess_attempt_count + 1,
                    AsrTask.heartbeat_at: now,
                    AsrTask.worker_id: self._worker_id,
                },
                synchronize_session=False,
            )
            db.commit()
            if not claimed:
                return
            postprocess_task = asyncio.create_task(self._process_postprocess_task(row.id))
            self._active_postprocess_tasks.add(postprocess_task)
            self._active_postprocess_ids.add(row.id)

            def discard_finished(done_task, claimed_task_id=row.id):
                self._active_postprocess_tasks.discard(done_task)
                self._active_postprocess_ids.discard(claimed_task_id)

            postprocess_task.add_done_callback(discard_finished)
        finally:
            db.close()

    async def _process_postprocess_task(self, task_id: int) -> None:
        await asyncio.to_thread(self._process_postprocess_task_sync, task_id)

    def _process_postprocess_task_sync(self, task_id: int) -> None:
        db = SessionLocal()
        try:
            task = db.get(AsrTask, task_id)
            if not task or task.status != "completed" or task.postprocess_status != "processing":
                return
            publish_task_event("asr", task, "postprocess_started", {"session_id": task.session_id})
            result = process_session_post_collection(db, task.session_id)
            task = db.get(AsrTask, task_id)
            task.postprocess_result = result
            task.postprocess_completed_at = datetime.utcnow()
            task.postprocess_status = "completed" if result["success"] else "failed"
            task.postprocess_error = "; ".join(
                f"{stage}: {error}" for stage, error in result.get("errors", {}).items()
            )[:2000] or None
            touch_task(task, self._worker_id)
            db.add(
                ScraperLog(
                    level="info" if result["success"] else "error",
                    message=(
                        f"场次 #{task.session_id} 话术、AI复盘与知识库处理"
                        f"{'完成' if result['success'] else '失败'}：话术 {result['transcript_count']} 段，"
                        f"复盘 {result['review_finding_count']} 条"
                    ),
                    raw_json={
                        "stage": "post_collection",
                        "event": "postprocess_completed" if result["success"] else "postprocess_failed",
                        "session_id": task.session_id,
                        "details": result,
                    },
                )
            )
            db.commit()
            publish_task_event(
                "asr",
                task,
                "postprocess_completed" if result["success"] else "postprocess_failed",
                result,
            )
        except Exception as exc:
            db.rollback()
            task = db.get(AsrTask, task_id)
            if task:
                task.postprocess_status = "failed"
                task.postprocess_error = str(exc)[:2000]
                task.postprocess_completed_at = datetime.utcnow()
                touch_task(task, self._worker_id)
                db.add(
                    ScraperLog(
                        level="error",
                        message=f"场次 #{task.session_id} 采集后处理失败: {str(exc)[:500]}",
                        raw_json={
                            "stage": "post_collection",
                            "event": "postprocess_failed",
                            "session_id": task.session_id,
                            "error": str(exc)[:500],
                        },
                    )
                )
                db.commit()
                publish_task_event("asr", task, "postprocess_failed", {"error": task.postprocess_error})
            logger.exception("任务 %s 采集后处理失败: %s", task_id, exc)
        finally:
            db.close()

    async def _process_task(self, task_id: int):
        """按分片处理 ASR 任务，已完成分片不会重复执行。"""
        async with self._semaphore:
            db = SessionLocal()
            try:
                task = db.get(AsrTask, task_id)
                if not task or task.status != "processing":
                    return
                ensure_task_identity(
                    task,
                    "asr",
                    f"asr:{task.task_type}:session:{task.session_id}",
                )
                task.error_message = None
                touch_task(task, self._worker_id)
                db.commit()
                publish_task_event("asr", task, "started", {"session_id": task.session_id})

                session = db.get(LiveSession, task.session_id)
                if not session:
                    raise RuntimeError("ASR 任务关联的直播场次不存在")
                stream = db.get(StreamSource, task.stream_id) if task.stream_id else None
                if not stream or not stream.m3u8_url:
                    raise RuntimeError("ASR 任务缺少真实直播流地址，请先刷新场次流地址")

                if should_handoff_realtime_task(task.task_type, session.live_status):
                    # 任务等候期间可能已经下播。实时任务的身份不能偷偷改成离线任务，
                    # 否则同一行任务会同时代表两种业务。这里明确结束初稿任务，再创建
                    # 一条独立的离线终稿任务。
                    task.status = TaskStatus.CANCELLED
                    task.error_message = "领取任务时直播已结束，已转交独立离线终稿任务"
                    task.completed_at = datetime.utcnow()
                    task.postprocess_status = "skipped"
                    touch_task(task, self._worker_id)
                    offline_task, _created = queue_session_transcription(db, session)
                    db.commit()
                    publish_task_event(
                        "asr",
                        task,
                        "handed_off_to_offline",
                        {"offline_task_id": offline_task.id},
                    )
                    return

                m3u8_url = stream.m3u8_url
                headers = dict(stream.headers_json) if stream and stream.headers_json else {}

                # ── 流地址自动刷新：转写前先探测 m3u8 是否有效 ──
                m3u8_url, stream = await self._auto_refresh_stream_if_expired(
                    db, task, m3u8_url, headers
                )

                is_live = task.task_type == "realtime"
                chunks = self._prepare_chunks(db, task, session, m3u8_url)

                while True:
                    for chunk in chunks:
                        self._ensure_task_running(db, task)
                        if chunk.status in {TaskStatus.COMPLETED, TaskStatus.SKIPPED}:
                            continue
                        while chunk.status != TaskStatus.COMPLETED and chunk.retry_count < chunk.max_retries:
                            self._ensure_task_running(db, task)
                            await self._wait_for_resource_slot(db, task)
                            try:
                                await self._process_chunk(
                                    db,
                                    task,
                                    chunk,
                                    m3u8_url,
                                    headers,
                                    is_live=is_live,
                                )
                            finally:
                                await self._release_resource_slot(task.id)
                            db.refresh(chunk)
                        if chunk.status not in {TaskStatus.COMPLETED, TaskStatus.SKIPPED}:
                            raise RuntimeError(
                                f"音频分片 {chunk.chunk_index + 1}/{len(chunks)} 达到最大重试次数: "
                                f"{chunk.error_message or '未知错误'}"
                            )
                        # 单 Worker 机器上，长离线回放不能把刚开播的实时任务堵几十分钟。
                        # 每完成一个 2 分钟分片就检查一次；有实时任务时保存当前断点并礼让。
                        if not is_live and self._has_queued_live_task(db, task.id):
                            requeue_offline_task_for_live_priority(task)
                            db.commit()
                            publish_task_event(
                                "asr",
                                task,
                                "yielded_to_live",
                                {"completed_chunk_index": chunk.chunk_index},
                            )
                            logger.info("任务 %s 已在分片边界礼让实时直播任务", task.id)
                            return

                    # 正在直播时按两分钟窗口继续追加，保证每段都有资源检查点。
                    db.refresh(session)
                    is_live = session.live_status == "live"
                    if not is_live:
                        break
                    index, start_seconds, end_seconds = next_live_chunk_range(
                        chunks,
                        settings.ASR_CHUNK_SECONDS,
                    )
                    next_chunk = AsrAudioChunk(
                        task_id=task.id,
                        session_id=task.session_id,
                        chunk_index=index,
                        start_seconds=start_seconds,
                        end_seconds=end_seconds,
                        source_url_hash=hashlib.sha256(m3u8_url.encode("utf-8")).hexdigest(),
                        status=TaskStatus.PENDING,
                        max_retries=max(1, settings.ASR_CHUNK_MAX_RETRIES),
                    )
                    db.add(next_chunk)
                    db.commit()
                    db.refresh(next_chunk)
                    chunks.append(next_chunk)
                    publish_task_event(
                        "asr",
                        task,
                        "live_chunk_created",
                        {"chunk_index": index, "start_seconds": start_seconds},
                    )

                segment_count = sum(
                    int(chunk.segment_count or 0)
                    for chunk in chunks
                    if chunk.status == TaskStatus.COMPLETED
                )
                if segment_count == 0:
                    raise RuntimeError("全部真实音频分片均未识别到有效话术，直播流可能已过期或没有人声")

                self._save_full_text(db, task, chunks)
                if task.task_type == "offline":
                    chunk_ids = [chunk.id for chunk in chunks]
                    # 离线分段处理期间使用隐藏暂存类型。只有全文成功写入后，才在同一
                    # 事务里公开终稿并删除直播初稿，页面不会看到两版混合或空窗。
                    db.query(TranscriptSegment).filter(
                        TranscriptSegment.asr_chunk_id.in_(chunk_ids),
                        TranscriptSegment.segment_type == "asr_offline_pending",
                    ).update(
                        {
                            TranscriptSegment.segment_type: "asr_offline",
                            TranscriptSegment.asr_status: "completed",
                        },
                        synchronize_session=False,
                    )
                    db.query(TranscriptSegment).filter(
                        TranscriptSegment.session_id == task.session_id,
                        TranscriptSegment.segment_type == "asr_realtime",
                    ).delete(synchronize_session=False)
                task.status = "completed"
                task.error_message = None
                task.completed_at = datetime.utcnow()
                task.postprocess_status = postprocess_status_for_task(task.task_type)
                task.postprocess_started_at = None
                task.postprocess_completed_at = None
                task.postprocess_error = None
                task.postprocess_attempt_count = 0
                task.postprocess_result = None
                touch_task(task, self._worker_id)
                db.commit()
                publish_task_event("asr", task, "completed", {"segment_count": segment_count, "chunk_count": len(chunks)})
                logger.info("任务 %s 完成: %s 个分片，%s 个话术片段", task_id, len(chunks), segment_count)

            except _YieldToLiveTask:
                db.rollback()
                task = db.get(AsrTask, task_id)
                if task and task.status == TaskStatus.PROCESSING:
                    requeue_offline_task_for_live_priority(task)
                    db.commit()
                    publish_task_event("asr", task, "yielded_to_live", {})
                logger.info("任务 %s 已在模型等待安全点礼让实时直播任务", task_id)
            except TaskCancellationRequested as exc:
                db.rollback()
                task = db.get(AsrTask, task_id)
                if task:
                    task.status = TaskStatus.CANCELLED
                    task.error_message = str(exc)[:500]
                    task.completed_at = datetime.utcnow()
                    task.postprocess_status = "skipped"
                    touch_task(task, self._worker_id)
                    db.commit()
                    publish_task_event("asr", task, "cancelled", {"message": task.error_message})
                logger.info("任务 %s 已按用户要求安全停止", task_id)
            except Exception as exc:
                logger.error("任务 %s 失败: %s", task_id, exc)
                # flush/commit 失败后 Session 会进入回滚状态，必须先恢复再记录任务结果。
                db.rollback()
                try:
                    task = db.get(AsrTask, task_id)
                    if task:
                        task.status = "failed"
                        task.error_message = str(exc)[:500]
                        task.completed_at = datetime.utcnow()
                        task.postprocess_status = "skipped"
                        touch_task(task, self._worker_id)
                        db.commit()
                        publish_task_event("asr", task, "failed", {"error": task.error_message})
                except Exception as persist_exc:
                    db.rollback()
                    logger.exception("任务 %s 失败状态保存异常: %s", task_id, persist_exc)
            finally:
                try:
                    plan = await asyncio.to_thread(self._current_resource_plan)
                    queue_auto_transcriptions(
                        db,
                        limit=max(0, plan.queue_capacity),
                        queue_capacity=plan.queue_capacity,
                    )
                except Exception as queue_exc:
                    db.rollback()
                    logger.warning("任务 %s 完成后补充 ASR 队列失败: %s", task_id, queue_exc)
                db.close()

    @staticmethod
    def _current_resource_plan() -> AsrResourcePlan:
        """读取系统总资源，而不是只看 ASR 自己的进程。"""
        return build_asr_resource_plan(get_system_usage())

    @staticmethod
    def _has_queued_live_task(db, current_task_id: int) -> bool:
        """只判断是否有其他正在直播的任务排队，不读取任何话术或客户数据。"""
        return (
            db.query(AsrTask.id)
            .join(LiveSession, LiveSession.id == AsrTask.session_id)
            .filter(
                AsrTask.id != current_task_id,
                AsrTask.status == TaskStatus.QUEUED,
                AsrTask.cancel_requested_at.is_(None),
                LiveSession.live_status == "live",
            )
            .first()
            is not None
        )

    async def _wait_for_resource_slot(self, db, task: AsrTask) -> None:
        """在每个音频分片边界按最新资源计划领取动态执行槽位。"""
        while self._running:
            self._ensure_task_running(db, task)
            plan = await asyncio.to_thread(self._current_resource_plan)
            acquired = False
            async with self._resource_slot_lock:
                if (
                    task.id in self._active_chunk_task_ids
                    or len(self._active_chunk_task_ids) < plan.target_concurrency
                ):
                    self._active_chunk_task_ids.add(task.id)
                    acquired = True
            if acquired:
                return

            # 暂停等待也持续写心跳，避免可靠任务回收器误判 Worker 已死亡。
            touch_task(task, self._worker_id)
            db.commit()
            if plan.message != self._last_resource_message:
                logger.info(plan.message)
                self._last_resource_message = plan.message
            await asyncio.sleep(max(2, settings.RESOURCE_SAMPLE_INTERVAL_SECONDS))
        raise TaskCancellationRequested("ASR Worker 正在停止，已保存完成分片")

    async def _release_resource_slot(self, task_id: int) -> None:
        """一个分片结束后释放动态槽位，让下一任务按最新资源重新竞争。"""
        async with self._resource_slot_lock:
            self._active_chunk_task_ids.discard(task_id)

    async def _ensure_funasr_alive(self) -> None:
        """确保 FunASR Docker 容器在运行；挂了就自动重启并等待模型加载。

        在每次分片转写前调用，避免 FunASR 容器 OOM 崩溃后
        Worker 傻等 300 秒超时才发现服务不可用。
        """
        # 1. 快速检查：容器是否在运行
        check = await asyncio.create_subprocess_shell(
            f"docker ps --filter name={self._FUNASR_CONTAINER} --format '{{{{.Status}}}}'",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await check.communicate()

        if stdout.decode().strip():
            return  # ✅ 容器在运行，连接问题交给 _process_chunk 的等待循环

        # 2. 容器没在跑 → 尝试重启
        logger.warning("⚠️ FunASR 容器未运行，尝试自动重启...")
        restart = await asyncio.create_subprocess_shell(
            f"docker restart {self._FUNASR_CONTAINER}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await restart.communicate()

        if restart.returncode != 0:
            raise RuntimeError(
                f"FunASR 容器重启失败（docker 返回码 {restart.returncode}），"
                f"请手动执行 docker restart {self._FUNASR_CONTAINER} 并检查 Docker 状态"
            )

        logger.info("✅ FunASR 容器重启成功，模型加载约需 18 秒，稍候...")

    async def _auto_refresh_stream_if_expired(
        self,
        db,
        task: AsrTask,
        m3u8_url: str,
        headers: dict,
    ) -> tuple[str, StreamSource | None]:
        """
        转写前先探测 m3u8 是否有效；如果过期则调后端 API 自动刷新。

        返回: (最终可用的 m3u8_url, 关联的 StreamSource 或 None)
        """
        # ── 1. 快速探测 ──
        logger.info("任务 %s: 探测流地址可用性...", task.id)
        health = await probe_stream_url(m3u8_url, headers, probe_seconds=2.0)

        if health["alive"]:
            logger.info("任务 %s: 流地址有效，直接开始转写", task.id)
            return m3u8_url, db.get(StreamSource, task.stream_id) if task.stream_id else None

        logger.warning(
            "任务 %s: 流地址已过期（%s），尝试自动刷新...",
            task.id,
            health.get("error", "未知原因"),
        )

        # ── 2. 调后端 API 自动刷新 ──
        refresh_url = f"{_BACKEND_BASE_URL}/live-sessions/{task.session_id}/refresh-stream"
        refresh_error_detail = ""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
                response = await client.post(
                    refresh_url,
                    headers={"X-Internal-Worker-Token": build_internal_worker_token()},
                )
                if response.status_code == 200:
                    data = response.json()
                    new_url = data.get("stream_url")
                    if new_url:
                        logger.info("任务 %s: 流地址自动刷新成功", task.id)
                        # 重新查询新的 StreamSource（API 已写入）
                        db.commit()  # 释放当前事务，让新数据可见
                        new_source = (
                            db.query(StreamSource)
                            .filter(
                                StreamSource.session_id == task.session_id,
                                StreamSource.status == "active",
                            )
                            .order_by(StreamSource.fetched_at.desc(), StreamSource.id.desc())
                            .first()
                        )
                        if new_source:
                            task.stream_id = new_source.id
                            db.commit()
                            return new_url, new_source
                        # 如果没找到新记录，直接用返回的 URL
                        return new_url, None
                    else:
                        logger.warning("任务 %s: 刷新 API 返回成功但无 stream_url", task.id)
                else:
                    error_detail = "未知错误"
                    try:
                        error_detail = response.json().get("detail", response.text[:200])
                    except Exception:
                        error_detail = response.text[:200]
                    refresh_error_detail = sanitize_ffmpeg_error(str(error_detail or "未知错误"))[:300]
                    logger.warning(
                        "任务 %s: 流地址刷新 API 返回 %s: %s",
                        task.id,
                        response.status_code,
                        error_detail,
                    )
        except Exception as exc:
            refresh_error_detail = sanitize_ffmpeg_error(str(exc))[:300]
            logger.error("任务 %s: 调用刷新 API 失败: %s", task.id, exc)

        # ── 3. 刷新失败，判断探测结果的确定性 ──
        error_msg = health.get("error", "")
        # 403/404/410/流地址已失效 → 明确过期，不再用原 URL 硬转
        is_definitely_expired = any(
            keyword.lower() in error_msg.lower()
            for keyword in ["403", "404", "410", "流地址已失效"]
        )
        if is_definitely_expired:
            refresh_hint = (
                f"自动刷新失败：{refresh_error_detail}。"
                if refresh_error_detail
                else "自动刷新失败。"
            )
            raise RuntimeError(
                f"流地址已失效（{error_msg}），{refresh_hint}无法继续转写。"
                "请检查直播回放是否仍可用，或手动重新采集流地址。"
            )

        # 探测不明确（网络波动/超时）→ 用原 URL 尝试，万一误判还能转成功
        logger.warning(
            "任务 %s: 自动刷新失败（%s），探测结果不明确，将使用原流地址继续尝试",
            task.id,
            error_msg or "未知原因",
        )
        return m3u8_url, db.get(StreamSource, task.stream_id) if task.stream_id else None

    @staticmethod
    def _ensure_task_running(db, task: AsrTask) -> None:
        """每个安全检查点都读取停止标记，避免把用户停止误记成失败。"""
        db.refresh(task)
        if task.cancel_requested_at or task.status == TaskStatus.CANCELLED:
            raise TaskCancellationRequested("用户已停止 ASR 转写，已完成分片会保留")

    def _prepare_chunks(self, db, task: AsrTask, session: LiveSession, m3u8_url: str) -> list[AsrAudioChunk]:
        """按最新真实时长幂等校准分片，不删除已经识别成功的话术。"""
        existing = (
            db.query(AsrAudioChunk)
            .filter(AsrAudioChunk.task_id == task.id)
            .order_by(AsrAudioChunk.chunk_index.asc())
            .all()
        )
        if existing:
            missing_ranges = reconcile_existing_chunks(
                existing,
                duration_seconds=max(0, int(session.live_duration_seconds or 0)),
                chunk_seconds=settings.ASR_CHUNK_SECONDS,
                is_live=session.live_status == "live",
            )
            source_hash = hashlib.sha256(m3u8_url.encode("utf-8")).hexdigest()
            for index, start_seconds, end_seconds in missing_ranges:
                chunk = AsrAudioChunk(
                    task_id=task.id,
                    session_id=task.session_id,
                    chunk_index=index,
                    start_seconds=start_seconds,
                    end_seconds=end_seconds,
                    source_url_hash=source_hash,
                    status=TaskStatus.PENDING,
                    max_retries=max(1, settings.ASR_CHUNK_MAX_RETRIES),
                )
                db.add(chunk)
                existing.append(chunk)
            db.commit()
            for chunk in existing:
                db.refresh(chunk)
            existing.sort(key=lambda item: int(item.chunk_index))
            return existing

        duration = max(0, int(session.live_duration_seconds or 0))
        ranges = build_chunk_ranges(
            duration,
            settings.ASR_CHUNK_SECONDS,
            is_live=session.live_status == "live",
        )
        source_hash = hashlib.sha256(m3u8_url.encode("utf-8")).hexdigest()
        chunks = []
        for index, (start_seconds, end_seconds) in enumerate(ranges):
            chunk = AsrAudioChunk(
                task_id=task.id,
                session_id=task.session_id,
                chunk_index=index,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                source_url_hash=source_hash,
                status="pending",
                max_retries=max(1, settings.ASR_CHUNK_MAX_RETRIES),
            )
            db.add(chunk)
            chunks.append(chunk)
        db.commit()
        for chunk in chunks:
            db.refresh(chunk)
        publish_task_event("asr", task, "chunks_created", {"chunk_count": len(chunks), "duration_seconds": duration})
        return chunks

    async def _process_chunk(self, db, task, chunk, m3u8_url, headers, *, is_live: bool = False) -> None:
        """执行单个真实音频分片；失败只回滚本分片的话术。"""
        client = FunasrClient()
        duration_seconds = (
            float(chunk.end_seconds - chunk.start_seconds)
            if chunk.end_seconds is not None
            else None
        )
        pipe = M3u8Pipe(
            m3u8_url,
            headers,
            # 实时流每次连接都从“当前直播点”读取，绝不能对持续流使用累计 -ss 偏移。
            # chunk.start_seconds 只负责把识别结果换算为整场时间轴。
            start_seconds=0 if is_live else chunk.start_seconds,
            duration_seconds=duration_seconds,
        )
        heartbeat_task: asyncio.Task | None = None
        try:
            chunk.status = "processing"
            chunk.retry_count += 1
            chunk.started_at = datetime.utcnow()
            chunk.completed_at = None
            chunk.worker_id = self._worker_id
            chunk.heartbeat_at = datetime.utcnow()
            chunk.error_message = None
            touch_task(task, self._worker_id)
            db.query(TranscriptSegment).filter(
                TranscriptSegment.asr_chunk_id == chunk.id
            ).delete(synchronize_session=False)
            db.commit()
            publish_task_event(
                "asr",
                task,
                "chunk_started",
                {"chunk_index": chunk.chunk_index, "retry_count": chunk.retry_count},
            )
            heartbeat_task = asyncio.create_task(
                self._heartbeat_active_chunk(task.id, chunk.id)
            )

            if not is_live and self._has_queued_live_task(db, task.id):
                raise _YieldToLiveTask

            async with self._funasr_connection_lock:
                try:
                    # 先确保 FunASR 容器在运行（挂了就自动重启）
                    await self._ensure_funasr_alive()
                    deadline = monotonic() + self._FUNASR_CONNECT_TIMEOUT
                    connected = await client.connect()
                    while not connected and monotonic() < deadline:
                        if not is_live and self._has_queued_live_task(db, task.id):
                            raise _YieldToLiveTask
                        logger.info("任务 %s 分片 %s 等待 FunASR 模型就绪", task.id, chunk.chunk_index)
                        await asyncio.sleep(3)
                        connected = await client.connect()
                    if not connected and not settings.asr_mock_enabled:
                        raise RuntimeError(
                            f"FunASR 服务在 {self._FUNASR_CONNECT_TIMEOUT} 秒内未就绪，"
                            f"请检查容器日志: docker logs {self._FUNASR_CONTAINER}"
                        )

                    expected_timeout = int((duration_seconds or 0) * 2) + 120
                    timeout = max(60, min(settings.ASR_TASK_TIMEOUT_SECONDS, expected_timeout))
                    segment_count = await asyncio.wait_for(
                        self._consume_transcription(db, task, chunk, client, pipe),
                        timeout=timeout,
                    )
                finally:
                    # 释放单连接锁以前先关掉旧连接，下一分片才不会撞进 C++ 容器。
                    await client.close()
            chunk.status = "completed"
            chunk.segment_count = segment_count
            chunk.completed_at = datetime.utcnow()
            chunk.heartbeat_at = datetime.utcnow()
            touch_task(task, self._worker_id)
            db.commit()
            publish_task_event(
                "asr",
                task,
                "chunk_completed",
                {"chunk_index": chunk.chunk_index, "segment_count": segment_count},
            )
        except _YieldToLiveTask:
            # 当前分片还没有完成，恢复为 pending 并退还刚领取的分片重试次数。
            # 任务本身由上层统一重新排队，避免被误记为取消或失败。
            db.rollback()
            chunk = db.get(AsrAudioChunk, chunk.id)
            if chunk:
                recover_interrupted_chunk(chunk)
                db.commit()
            raise
        except TaskCancellationRequested:
            # 停止不是失败，当前分片恢复为待处理，后续重试可继续使用已完成分片。
            db.rollback()
            chunk = db.get(AsrAudioChunk, chunk.id)
            task = db.get(AsrTask, task.id)
            if chunk and task:
                chunk.status = TaskStatus.PENDING
                chunk.error_message = "用户停止任务，等待下次断点续传"
                chunk.completed_at = None
                touch_task(task, self._worker_id)
                db.commit()
            raise
        except Exception as exc:
            # 分片写入若触发数据库异常，先恢复事务再保存可重试状态。
            db.rollback()
            chunk = db.get(AsrAudioChunk, chunk.id)
            task = db.get(AsrTask, task.id)
            if not chunk or not task:
                raise
            chunk.status = "failed"
            chunk.error_message = build_chunk_failure_message(exc, pipe)
            chunk.completed_at = datetime.utcnow()
            chunk.heartbeat_at = datetime.utcnow()
            touch_task(task, self._worker_id)
            db.commit()
            publish_task_event(
                "asr",
                task,
                "chunk_failed",
                {"chunk_index": chunk.chunk_index, "error": chunk.error_message},
            )
            logger.warning(
                "任务 %s 分片 %s 第 %s/%s 次失败: %s",
                task.id,
                chunk.chunk_index,
                chunk.retry_count,
                chunk.max_retries,
                exc,
            )
        finally:
            if heartbeat_task:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
            await pipe.close()
            await client.close()

    async def _heartbeat_active_chunk(self, task_id: int, chunk_id: int) -> None:
        """长时间取流期间独立写心跳，避免主会话等待音频时看起来像“卡死”。"""
        interval = max(10, min(30, settings.TASK_HEARTBEAT_TIMEOUT_SECONDS // 3))
        while self._running:
            await asyncio.sleep(interval)
            heartbeat_db = SessionLocal()
            try:
                now = datetime.utcnow()
                heartbeat_db.query(AsrTask).filter(
                    AsrTask.id == task_id,
                    AsrTask.status == TaskStatus.PROCESSING,
                ).update(
                    {
                        AsrTask.heartbeat_at: now,
                        AsrTask.worker_id: self._worker_id,
                    },
                    synchronize_session=False,
                )
                heartbeat_db.query(AsrAudioChunk).filter(
                    AsrAudioChunk.id == chunk_id,
                    AsrAudioChunk.status == TaskStatus.PROCESSING,
                ).update(
                    {
                        AsrAudioChunk.heartbeat_at: now,
                        AsrAudioChunk.worker_id: self._worker_id,
                    },
                    synchronize_session=False,
                )
                heartbeat_db.commit()
            except Exception as exc:
                heartbeat_db.rollback()
                logger.warning("任务 %s 分片 %s 心跳更新失败: %s", task_id, chunk_id, exc)
            finally:
                heartbeat_db.close()

    def _save_full_text(self, db, task: AsrTask, chunks: list[AsrAudioChunk]) -> bool:
        """保存全文缓存；迁移前字段过短时保留真实分段并允许任务完成。"""
        chunk_ids = [chunk.id for chunk in chunks]
        segments = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.asr_chunk_id.in_(chunk_ids))
            .order_by(TranscriptSegment.segment_start.asc())
            .all()
        )
        full_text = "\n".join(
            f"[{float(segment.segment_start):.1f}s] {segment.text_content}"
            for segment in segments
            if segment.text_content
        )
        existing = db.query(TranscriptFullText).filter(
            TranscriptFullText.session_id == task.session_id
        ).first()
        if existing:
            existing.full_text = full_text
        else:
            db.add(TranscriptFullText(session_id=task.session_id, full_text=full_text))
        try:
            # 与任务 completed 状态在同一事务提交，避免全文成功但任务状态未更新。
            db.flush()
            return True
        except DataError as exc:
            db.rollback()
            if not is_full_text_too_long_error(exc):
                raise
            logger.warning(
                "任务 %s 全文超过旧 TEXT 容量，保留 %s 个真实分段并等待 LONGTEXT 迁移",
                task.id,
                len(segments),
            )
            return False

    async def _consume_transcription(self, db, task, chunk, client, pipe) -> int:
        """消费一个分片的 ASR 结果，并换算为整场绝对时间。"""
        segment_count = 0
        offset = float(chunk.start_seconds or 0)
        async for result in client.transcribe(
            task.session_id,
            pipe.read_frames(),
            task_type=task.task_type,
        ):
            self._ensure_task_running(db, task)
            absolute_result = dict(result)
            absolute_result["segment_start"] = offset + float(result.get("segment_start") or 0)
            absolute_result["segment_end"] = offset + float(result.get("segment_end") or 0)
            # 行业知识纠错：对 ASR 输出的原始文本做品牌名和术语校正
            raw_text = absolute_result.get("text", "")
            corrected_text = correct_asr_text(raw_text) if raw_text else ""
            absolute_result["text"] = corrected_text
            segment = TranscriptSegment(
                session_id=task.session_id,
                asr_chunk_id=chunk.id,
                segment_start=absolute_result["segment_start"],
                segment_end=absolute_result["segment_end"],
                text_content=corrected_text,
                asr_status="processing" if task.task_type == "offline" else "completed",
                segment_type=segment_type_for_task(task.task_type),
            )
            db.add(segment)
            chunk.segment_count = segment_count + 1
            chunk.heartbeat_at = datetime.utcnow()
            touch_task(task, self._worker_id)
            db.commit()
            segment_count += 1
            if task.task_type == "realtime":
                # 离线终稿在完整成功以前必须保持隐藏，不能通过 WebSocket 偷跑半成品。
                await ws_manager.publish_asr_result(task.session_id, absolute_result)

        return segment_count


async def main():
    worker = AsrWorker()

    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("收到停止信号，ASR Worker 关闭中...")
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass

    # 启动 Worker
    worker_task = asyncio.create_task(worker.run())

    await stop_event.wait()
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass

    await ws_manager.close()
    logger.info("ASR Worker 已退出")


if __name__ == "__main__":
    asyncio.run(main())
