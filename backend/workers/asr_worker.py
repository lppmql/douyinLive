"""
ASR Worker 进程 — 独立运行的话术转写服务

从 DB 轮询 asr_tasks，通过 ffmpeg pipe 拉流 → FunASR 识别 → 写入 transcript_segments

启动:
    cd backend && source .venv/bin/activate
    python -m workers.asr_worker

环境变量:
    ASR_WORKER_MODE=true
    ASR_DYNAMIC_MAX_TASKS=2
"""

import asyncio
import hashlib
import os
import signal
from pathlib import Path
from time import monotonic
from datetime import datetime, timedelta

import httpx
from sqlalchemy import and_, or_
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
from app.services.asr.chunks import (
    build_chunk_ranges,
    next_live_chunk_range,
    reconcile_existing_chunks,
)
from app.services.asr.m3u8_pipe import M3u8Pipe, sanitize_ffmpeg_error
from app.services.asr.audio_buffer import (
    PCM_BYTES_PER_SECOND,
    LiveAudioBuffer,
    prune_audio_buffers,
)
from app.services.asr.transcript_quality import elapsed_live_seconds
from app.services.asr.funasr_client import FunasrClient
from app.services.asr.timestamp_alignment import (
    remap_corrected_text,
    shift_word_timestamps,
)
from app.services.asr.lane_scheduler import AsrLaneCoordinator
from app.services.asr.queue import (
    get_active_manual_task,
    get_dispatch_policy,
    list_queued_task_ids_for_available_lanes,
    queue_auto_transcriptions,
    queue_session_transcription,
    recover_interrupted_chunk,
    requeue_task_for_dispatch,
    requeue_offline_task_for_live_priority,
)
from app.services.asr.websocket_manager import ws_manager
from app.services.asr.corrector import correct_text as correct_asr_text
from app.services.asr.control import (
    clear_asr_worker_heartbeat,
    write_asr_worker_heartbeat,
)
from app.services.clips.auto_queue import queue_clip_after_offline_final
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
from app.services.transcript_compliance import (
    load_enabled_compliance_rules,
    match_compliance_text,
)

# ASR Worker 调用后端 API 的基地址（同机部署）
_BACKEND_BASE_URL = "http://localhost:8000/api/v1"


class _YieldToLiveTask(Exception):
    """离线任务在安全点主动礼让实时直播，不属于失败或人工取消。"""


class _YieldToManualTask(Exception):
    """自动任务在安全点礼让人工独占任务，不属于失败或取消。"""


class _CompletenessRepairLimitExceeded(RuntimeError):
    """真实时长连续增长超过自动补齐上限，需要人工核对采集时长。"""


def advance_completeness_repair_round(current_round: int, max_rounds: int) -> int:
    """推进完整度补齐轮次，超过硬上限立即停止自动循环。"""
    next_round = max(0, int(current_round)) + 1
    if next_round > max(1, int(max_rounds)):
        raise _CompletenessRepairLimitExceeded(
            f"话术完整度已自动补齐 {max_rounds} 轮，"
            "真实直播时长仍在变化，请先核对场次结束时间"
        )
    return next_round


def is_full_text_too_long_error(exc: DataError) -> bool:
    """识别迁移前 MySQL TEXT 容量不足错误。"""
    return bool(
        getattr(exc, "orig", None)
        and getattr(exc.orig, "args", ())
        and exc.orig.args[0] == 1406
    )


def segment_type_for_task(task_type: str) -> str:
    """离线终稿完成前先写入隐藏暂存类型，实时初稿则立即可见。"""
    return "asr_offline_pending" if task_type == "offline" else "asr_realtime"


def should_handoff_realtime_task(task_type: str, live_status: str) -> bool:
    """实时任务被领取时若已经下播，就交给新离线任务而不是篡改任务类型。"""
    return task_type == "realtime" and live_status != "live"


def should_handoff_realtime_failure(
    task_type: str,
    live_status: str,
    error_message: str,
) -> bool:
    """识别最后一段时刚好下播，应平滑转交终稿而不是把整场记为失败。"""
    if task_type != "realtime" or live_status == "live":
        return False
    message = (error_message or "").lower()
    return any(
        marker in message
        for marker in (
            "未输出任何音频帧",
            "404",
            "流地址已失效",
            "直播音频缓存等待超时",
            # 直播收尾时缓存停止增长也会读不满 120 秒窗口，属于正常下播场景，
            # 应转交离线终稿补齐而不是把整场实时任务标成失败。
            "直播音频缓存不完整",
        )
    )


def postprocess_status_for_task(task_type: str) -> str:
    """ASR 只负责转写；AI 复盘已改为人工生成，旧后处理状态统一跳过。"""
    return "skipped"


def build_chunk_failure_message(error: Exception, pipe: object | None = None) -> str:
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


def should_refresh_stream_after_chunk_failure(
    task_type: str, error_message: str
) -> bool:
    """离线分片遇到取流错误时应刷新地址，而不是继续重试同一个坏 URL。"""
    if task_type != "offline":
        return False
    message = (error_message or "").casefold()
    return any(
        marker in message
        for marker in (
            "未输出任何音频帧",
            "404",
            "403",
            "410",
            "input/output error",
            "connection reset",
            "connection refused",
            "tls",
            "流地址已失效",
        )
    )


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
        # 两个逻辑任务可以同时准备，但真正连接 FunASR 时仍然严格单连接。
        self._lane_coordinator = AsrLaneCoordinator(settings.ASR_LIVE_CHUNK_QUOTA)
        self._audio_buffers: dict[int, LiveAudioBuffer] = {}
        self._audio_buffer_lock = asyncio.Lock()
        self._audio_buffer_dir = (
            Path(__file__).resolve().parents[2] / "data" / "asr-buffer"
        )
        self._last_resource_message = ""
        self._running = False
        self._poll_interval = 5  # 秒
        self._worker_id = current_worker_id("asr")

    async def run(self):
        """主循环"""
        self._running = True
        write_asr_worker_heartbeat(self._worker_id)
        logger.info(
            "ASR Worker 启动（资源自适应并发，安全上限: %s）",
            settings.ASR_DYNAMIC_MAX_TASKS,
        )
        self._recover_stale_tasks(recover_all=True)

        while self._running:
            try:
                write_asr_worker_heartbeat(self._worker_id)
                await self._poll_tasks()
                write_asr_worker_heartbeat(self._worker_id)
                # AI 复盘由详情页手动生成，知识库和 DataEase 由后台自动同步。
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"ASR Worker 异常: {e}")
                await asyncio.sleep(10)

    async def shutdown(self) -> None:
        """停止领取任务，并尽量在外部强制清理期限前结束全部子协程。"""
        self._running = False
        pending_tasks = [task for task in self._active_tasks if not task.done()]
        for task in pending_tasks:
            task.cancel()
        if pending_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*pending_tasks, return_exceptions=True), timeout=6
                )
            except asyncio.TimeoutError:
                logger.warning("ASR 子任务未在 6 秒内退出，将由运行时控制器清理")
        async with self._audio_buffer_lock:
            buffers = list(self._audio_buffers.values())
            self._audio_buffers.clear()
        for buffer in buffers:
            await buffer.stop()

    def _recover_stale_tasks(self, recover_all: bool = False):
        """回收重启遗留或心跳超时的任务，并保留已完成分片。"""
        db = SessionLocal()
        try:
            query = db.query(AsrTask).filter(AsrTask.status == "processing")
            if not recover_all:
                cutoff = datetime.utcnow() - timedelta(
                    seconds=max(60, settings.TASK_HEARTBEAT_TIMEOUT_SECONDS)
                )
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
                chunks = (
                    db.query(AsrAudioChunk)
                    .filter(
                        AsrAudioChunk.task_id == task.id,
                        AsrAudioChunk.status == "processing",
                    )
                    .all()
                )
                for chunk in chunks:
                    recover_interrupted_chunk(chunk)
            if stale:
                db.commit()
                for task in stale:
                    publish_task_event(
                        "asr", task, "recovered", {"status": task.status}
                    )
                logger.warning("Worker 从断点回收 %s 个遗留 ASR 任务", len(stale))

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
                limit=settings.ASR_MAX_QUEUED,
                queue_capacity=settings.ASR_MAX_QUEUED,
            )
            if available_slots == 0:
                return
            occupied_lanes = (
                {
                    str(row[0])
                    for row in (
                        db.query(AsrTask.task_type)
                        .filter(AsrTask.id.in_(self._active_task_ids))
                        .distinct()
                        .all()
                    )
                }
                if self._active_task_ids
                else set()
            )
            queued_ids = list_queued_task_ids_for_available_lanes(
                db,
                min(plan.queue_capacity, available_slots),
                occupied_lanes=occupied_lanes,
            )

            for task_id in queued_ids:
                now = datetime.utcnow()
                claimed = (
                    db.query(AsrTask)
                    .filter(
                        AsrTask.id == task_id,
                        AsrTask.status == "queued",
                        AsrTask.cancel_requested_at.is_(None),
                    )
                    .update(
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

    async def _start_live_audio_buffer(
        self,
        session: LiveSession,
        m3u8_url: str,
        headers: dict[str, str],
    ) -> LiveAudioBuffer | None:
        """串行完成容量分配和注册，避免两场直播重复领取同一份额度。"""
        if not settings.ASR_AUDIO_BUFFER_ENABLED:
            return None
        async with self._audio_buffer_lock:
            return await self._start_live_audio_buffer_locked(
                session,
                m3u8_url,
                headers,
            )

    async def _start_live_audio_buffer_locked(
        self,
        session: LiveSession,
        m3u8_url: str,
        headers: dict[str, str],
    ) -> LiveAudioBuffer | None:
        """在容量锁内为直播启动独立录音。"""
        existing = self._audio_buffers.get(session.id)
        if existing and existing.is_running:
            return existing

        capacity_bytes = int(settings.ASR_AUDIO_BUFFER_MAX_GB * 1024**3)
        protected_buffers = list(self._audio_buffers.values())
        protected_paths = {item.audio_path for item in protected_buffers}
        prune_audio_buffers(
            self._audio_buffer_dir,
            retention_hours=settings.ASR_AUDIO_BUFFER_RETENTION_HOURS,
            max_bytes=capacity_bytes,
            protected_paths=protected_paths,
        )
        running_allocated = sum(
            item.max_bytes for item in protected_buffers if item.is_running
        )
        stopped_protected_size = sum(
            int(item.audio_path.stat().st_size)
            for item in protected_buffers
            if not item.is_running and item.audio_path.exists()
        )
        known_paths = {item.resolve() for item in protected_paths}
        unprotected_size = sum(
            int(item.stat().st_size)
            for item in self._audio_buffer_dir.glob("session-*.pcm")
            if item.is_file() and item.resolve() not in known_paths
        )
        available_bytes = max(
            0,
            capacity_bytes
            - running_allocated
            - stopped_protected_size
            - unprotected_size,
        )
        minimum_buffer_bytes = settings.ASR_CHUNK_SECONDS * PCM_BYTES_PER_SECOND
        if available_bytes < minimum_buffer_bytes and unprotected_size:
            # 新直播至少要能保存一个完整分片；空间不足时优先清理不再被当前
            # Worker 引用的旧文件，运行中和待终稿复用的文件绝不删除。
            prune_audio_buffers(
                self._audio_buffer_dir,
                retention_hours=settings.ASR_AUDIO_BUFFER_RETENTION_HOURS,
                max_bytes=running_allocated + stopped_protected_size,
                protected_paths=protected_paths,
            )
            # 清理函数会保留受保护文件，也可能保留仍未超过目标的旧文件；
            # 必须重新读取真实磁盘占用，不能假设旧缓存已经全部删除。
            unprotected_size = sum(
                int(item.stat().st_size)
                for item in self._audio_buffer_dir.glob("session-*.pcm")
                if item.is_file() and item.resolve() not in known_paths
            )
            available_bytes = max(
                0,
                capacity_bytes
                - running_allocated
                - stopped_protected_size
                - unprotected_size,
            )
        if available_bytes < minimum_buffer_bytes:
            logger.warning(
                "场次 %s 无法启动连续缓存：2GB 总额度已被运行中或待补齐场次占用",
                session.id,
            )
            return None

        elapsed_seconds = elapsed_live_seconds(session.live_start_time)
        audio_buffer = LiveAudioBuffer(
            session.id,
            m3u8_url,
            headers,
            timeline_start_seconds=elapsed_seconds,
            buffer_dir=self._audio_buffer_dir,
            max_bytes=available_bytes,
        )
        await audio_buffer.start()
        self._audio_buffers[session.id] = audio_buffer
        return audio_buffer

    def _handoff_realtime_to_offline(
        self,
        db,
        task: AsrTask,
        session: LiveSession,
        message: str,
    ) -> AsrTask:
        """保留已完成直播初稿并创建独立终稿任务。"""
        completed_chunk_exists = (
            db.query(AsrAudioChunk.id)
            .filter(
                AsrAudioChunk.task_id == task.id,
                AsrAudioChunk.status == TaskStatus.COMPLETED,
            )
            .first()
            is not None
        )
        task.status = (
            TaskStatus.COMPLETED if completed_chunk_exists else TaskStatus.CANCELLED
        )
        task.error_message = message[:500]
        task.completed_at = datetime.utcnow()
        task.postprocess_status = "skipped"
        touch_task(task, self._worker_id)
        offline_task, _created = queue_session_transcription(
            db,
            session,
            queue_source=task.queue_source or "auto",
        )
        db.commit()
        publish_task_event(
            "asr",
            task,
            "handed_off_to_offline",
            {"offline_task_id": offline_task.id, "message": task.error_message},
        )
        return offline_task

    async def _process_task(self, task_id: int):
        """按分片处理 ASR 任务，已完成分片不会重复执行。"""
        async with self._semaphore:
            db = SessionLocal()
            live_audio_buffer: LiveAudioBuffer | None = None
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
                publish_task_event(
                    "asr", task, "started", {"session_id": task.session_id}
                )

                session = db.get(LiveSession, task.session_id)
                if not session:
                    raise RuntimeError("ASR 任务关联的直播场次不存在")
                stream = (
                    db.get(StreamSource, task.stream_id) if task.stream_id else None
                )
                if not stream or not stream.m3u8_url:
                    raise RuntimeError("ASR 任务缺少真实直播流地址，请先刷新场次流地址")

                if should_handoff_realtime_task(task.task_type, session.live_status):
                    # 任务等候期间可能已经下播。实时任务的身份不能偷偷改成离线任务，
                    # 否则同一行任务会同时代表两种业务。这里明确结束初稿任务，再创建
                    # 一条独立的离线终稿任务。
                    self._handoff_realtime_to_offline(
                        db,
                        task,
                        session,
                        "领取任务时直播已结束，已转交独立离线终稿任务",
                    )
                    return

                m3u8_url = stream.m3u8_url
                headers = (
                    dict(stream.headers_json) if stream and stream.headers_json else {}
                )

                # ── 流地址自动刷新：转写前先探测 m3u8 是否有效 ──
                m3u8_url, stream = await self._auto_refresh_stream_if_expired(
                    db, task, m3u8_url, headers
                )
                if stream and stream.headers_json:
                    # 刷新后的地址可能依赖新的 Referer/User-Agent，不能继续沿用
                    # 旧 StreamSource 的请求头（旧数据里的 UA 还可能多一层引号）。
                    headers = dict(stream.headers_json)

                is_live = task.task_type == "realtime"
                if is_live:
                    live_audio_buffer = await self._start_live_audio_buffer(
                        session,
                        m3u8_url,
                        headers,
                    )
                else:
                    # 刚下播时优先复用本 Worker 留下的真实 PCM；缓存未覆盖的旧区间
                    # 仍从回放拉取，不能拿别的时间段冒充。
                    live_audio_buffer = self._audio_buffers.get(session.id)
                chunks = self._prepare_chunks(
                    db,
                    task,
                    session,
                    m3u8_url,
                    live_buffer_start_seconds=(
                        live_audio_buffer.timeline_start_seconds
                        if is_live and live_audio_buffer
                        else None
                    ),
                )

                completeness_repair_rounds = 0
                while True:
                    for chunk in chunks:
                        self._ensure_task_running(db, task)
                        if chunk.status in {TaskStatus.COMPLETED, TaskStatus.SKIPPED}:
                            continue
                        # slow_seek_retried 只作用于当前分片：fast-seek 定位失败后，
                        # 下一次尝试改用精确定位，不让其它分片背负这个标志。
                        slow_seek_retried = False
                        while (
                            chunk.status
                            not in {
                                TaskStatus.COMPLETED,
                                TaskStatus.SKIPPED,
                            }
                            and chunk.retry_count < chunk.max_retries
                        ):
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
                                    audio_buffer=live_audio_buffer,
                                    seek_mode=("slow" if slow_seek_retried else "fast"),
                                )
                            finally:
                                await self._release_resource_slot(task.id)
                            db.refresh(chunk)
                            if (
                                chunk.status == TaskStatus.FAILED
                                and chunk.retry_count < chunk.max_retries
                            ):
                                # 离线分片读到 0 帧时先按分片起点分类，避免两种误判：
                                # 1) 分片起点已超出回放真实时长 → 内容不存在，安全跳过；
                                # 2) 地址有效但 fast-seek 在 HLS 末尾定位越界 → slow-seek 兜底。
                                # 两者都不该反复刷新同一个其实没有问题的地址。
                                if not is_live:
                                    boundary = await self._classify_chunk_failure(
                                        db,
                                        task,
                                        chunk,
                                        m3u8_url,
                                        headers,
                                    )
                                    if boundary == "skip":
                                        chunk.status = TaskStatus.SKIPPED
                                        chunk.error_message = "分片起点超出回放真实时长，该区间在回放中不存在，已安全跳过"
                                        chunk.completed_at = datetime.utcnow()
                                        db.commit()
                                        publish_task_event(
                                            "asr",
                                            task,
                                            "chunk_skipped_out_of_bounds",
                                            {
                                                "chunk_index": chunk.chunk_index,
                                                "start_seconds": chunk.start_seconds,
                                            },
                                        )
                                        continue
                                    if (
                                        boundary == "slow_retry"
                                        and not slow_seek_retried
                                    ):
                                        slow_seek_retried = True
                                        chunk.status = TaskStatus.PENDING
                                        chunk.error_message = (
                                            "fast-seek 定位未读到音频，改用精确定位重试"
                                        )
                                        db.commit()
                                        publish_task_event(
                                            "asr",
                                            task,
                                            "chunk_slow_seek_retry",
                                            {"chunk_index": chunk.chunk_index},
                                        )
                                        continue
                                if should_refresh_stream_after_chunk_failure(
                                    task.task_type,
                                    chunk.error_message or "",
                                ):
                                    # 第一次失败后立即强制刷新，第二次尝试使用新地址。
                                    # 已完成分片保持不动，因此这里是真正的断点续传。
                                    previous_stream_id = task.stream_id
                                    (
                                        refreshed_url,
                                        refreshed_source,
                                    ) = await self._auto_refresh_stream_if_expired(
                                        db,
                                        task,
                                        m3u8_url,
                                        headers,
                                        force_refresh=True,
                                    )
                                    if refreshed_url != m3u8_url or (
                                        refreshed_source is not None
                                        and refreshed_source.id != previous_stream_id
                                    ):
                                        m3u8_url = refreshed_url
                                        if (
                                            refreshed_source
                                            and refreshed_source.headers_json
                                        ):
                                            headers = dict(
                                                refreshed_source.headers_json
                                            )
                                        chunk.source_url_hash = hashlib.sha256(
                                            m3u8_url.encode("utf-8")
                                        ).hexdigest()
                                        chunk.status = TaskStatus.PENDING
                                        chunk.error_message = (
                                            "回放地址已自动刷新，正在从当前分片继续"
                                        )
                                        db.commit()
                                        publish_task_event(
                                            "asr",
                                            task,
                                            "stream_refreshed_for_chunk_retry",
                                            {"chunk_index": chunk.chunk_index},
                                        )
                        if chunk.status not in {
                            TaskStatus.COMPLETED,
                            TaskStatus.SKIPPED,
                        }:
                            db.refresh(session)
                            if should_handoff_realtime_failure(
                                task.task_type,
                                session.live_status,
                                chunk.error_message or "",
                            ):
                                if live_audio_buffer:
                                    await live_audio_buffer.stop()
                                self._handoff_realtime_to_offline(
                                    db,
                                    task,
                                    session,
                                    "直播在最后分片读取时结束，已保留初稿并自动转交离线终稿补齐",
                                )
                                return
                            raise RuntimeError(
                                f"音频分片 {chunk.chunk_index + 1}/{len(chunks)} 达到最大重试次数: "
                                f"{chunk.error_message or '未知错误'}"
                            )
                        # 单 Worker 机器上，长离线回放不能把刚开播的实时任务堵几十分钟。
                        # 每完成一个 2 分钟分片就检查一次；有实时任务时保存当前断点并礼让。
                        if self._should_yield_to_manual(db, task):
                            requeue_task_for_dispatch(
                                task, "人工选择了优先场次，已保存断点并暂停"
                            )
                            db.commit()
                            publish_task_event(
                                "asr",
                                task,
                                "yielded_to_manual",
                                {"completed_chunk_index": chunk.chunk_index},
                            )
                            logger.info("任务 %s 已在分片边界礼让人工独占任务", task.id)
                            return
                        if (
                            task.queue_source != "manual"
                            and not is_live
                            and self._has_queued_live_task(db, task.id)
                        ):
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
                        if (
                            task.queue_source != "manual"
                            and not is_live
                            and self._has_newer_queued_offline_task(db, task)
                        ):
                            requeue_offline_task_for_live_priority(task)
                            task.error_message = (
                                "已保存当前断点，先处理最新结束的直播终稿"
                            )
                            db.commit()
                            publish_task_event(
                                "asr",
                                task,
                                "yielded_to_latest_offline",
                                {"completed_chunk_index": chunk.chunk_index},
                            )
                            logger.info("任务 %s 已在分片边界礼让最新下播终稿", task.id)
                            return

                    # 离线任务完成本轮后必须按最新真实时长再校准一次。采集服务可能
                    # 在转写期间修正下播时长；新增长度只追加缺失区间，不重跑旧片。
                    db.refresh(session)
                    if task.task_type == "offline":
                        refreshed_chunks = self._prepare_chunks(
                            db,
                            task,
                            session,
                            m3u8_url,
                        )
                        incomplete_chunks = [
                            item
                            for item in refreshed_chunks
                            if item.status
                            not in {TaskStatus.COMPLETED, TaskStatus.SKIPPED}
                        ]
                        if incomplete_chunks:
                            completeness_repair_rounds = (
                                advance_completeness_repair_round(
                                    completeness_repair_rounds,
                                    settings.ASR_COMPLETENESS_REPAIR_ROUNDS,
                                )
                            )
                            chunks = refreshed_chunks
                            publish_task_event(
                                "asr",
                                task,
                                "missing_ranges_appended",
                                {
                                    "missing_chunk_count": len(incomplete_chunks),
                                    "duration_seconds": int(
                                        session.live_duration_seconds or 0
                                    ),
                                },
                            )
                            continue
                        if live_audio_buffer:
                            await live_audio_buffer.stop()
                        break

                    # 正在直播时按两分钟窗口继续追加，保证每段都有资源检查点。
                    is_live = session.live_status == "live"
                    if not is_live:
                        if live_audio_buffer:
                            await live_audio_buffer.stop()
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
                        source_url_hash=hashlib.sha256(
                            m3u8_url.encode("utf-8")
                        ).hexdigest(),
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
                publish_task_event(
                    "asr",
                    task,
                    "completed",
                    {"segment_count": segment_count, "chunk_count": len(chunks)},
                )
                logger.info(
                    "任务 %s 完成: %s 个分片，%s 个话术片段",
                    task_id,
                    len(chunks),
                    segment_count,
                )
                if task.task_type == "offline":
                    # 只响应本次新完成的离线终稿事件，不扫描历史任务，也不触发 AI 复盘。
                    queue_clip_after_offline_final(
                        task.session_id,
                        asr_task_id=task.id,
                    )

            except _YieldToLiveTask:
                db.rollback()
                task = db.get(AsrTask, task_id)
                if task and task.status == TaskStatus.PROCESSING:
                    requeue_offline_task_for_live_priority(task)
                    db.commit()
                    publish_task_event("asr", task, "yielded_to_live", {})
                logger.info("任务 %s 已在模型等待安全点礼让实时直播任务", task_id)
            except _YieldToManualTask:
                db.rollback()
                task = db.get(AsrTask, task_id)
                if task and task.status == TaskStatus.PROCESSING:
                    requeue_task_for_dispatch(
                        task, "人工选择了优先场次，已保存断点并暂停"
                    )
                    db.commit()
                    publish_task_event("asr", task, "yielded_to_manual", {})
                logger.info("任务 %s 已在模型等待安全点礼让人工独占任务", task_id)
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
                    publish_task_event(
                        "asr", task, "cancelled", {"message": task.error_message}
                    )
                logger.info("任务 %s 已按用户要求安全停止", task_id)
            except Exception as exc:
                logger.error("任务 %s 失败: %s", task_id, exc)
                # flush/commit 失败后 Session 会进入回滚状态，必须先恢复再记录任务结果。
                db.rollback()
                try:
                    task = db.get(AsrTask, task_id)
                    if task:
                        should_auto_repair = (
                            task.task_type == "offline"
                            and int(task.retry_count or 0) < int(task.max_retries or 3)
                            and not isinstance(exc, _CompletenessRepairLimitExceeded)
                        )
                        task.status = (
                            TaskStatus.QUEUED
                            if should_auto_repair
                            else TaskStatus.FAILED
                        )
                        task.error_message = (
                            f"完整度补齐第 {task.retry_count} 轮未完成，已自动续接：{exc}"
                            if should_auto_repair
                            else str(exc)
                        )[:500]
                        task.completed_at = (
                            None if should_auto_repair else datetime.utcnow()
                        )
                        task.postprocess_status = "skipped"
                        touch_task(task, self._worker_id)
                        db.commit()
                        publish_task_event(
                            "asr",
                            task,
                            "repair_queued" if should_auto_repair else "failed",
                            {"error": task.error_message},
                        )
                except Exception as persist_exc:
                    db.rollback()
                    logger.exception(
                        "任务 %s 失败状态保存异常: %s", task_id, persist_exc
                    )
            finally:
                if live_audio_buffer and live_audio_buffer.is_running:
                    await live_audio_buffer.stop()
                try:
                    finished_task = db.get(AsrTask, task_id)
                    if (
                        finished_task
                        and finished_task.task_type == "offline"
                        and finished_task.status
                        in {
                            TaskStatus.COMPLETED,
                            TaskStatus.FAILED,
                            TaskStatus.CANCELLED,
                        }
                    ):
                        async with self._audio_buffer_lock:
                            self._audio_buffers.pop(finished_task.session_id, None)
                    queue_auto_transcriptions(
                        db,
                        limit=settings.ASR_MAX_QUEUED,
                        queue_capacity=settings.ASR_MAX_QUEUED,
                    )
                except Exception as queue_exc:
                    db.rollback()
                    logger.warning(
                        "任务 %s 完成后补充 ASR 队列失败: %s", task_id, queue_exc
                    )
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

    @staticmethod
    def _has_manual_task(db, current_task_id: int) -> bool:
        """判断是否有另一条人工排队或处理中任务。"""
        return get_active_manual_task(db, exclude_task_id=current_task_id) is not None

    @staticmethod
    def _should_yield_to_manual(db, current_task: AsrTask) -> bool:
        """自动任务在分片或模型等待边界礼让人工任务，人工任务自身不礼让。"""
        return current_task.queue_source != "manual" and AsrWorker._has_manual_task(
            db, current_task.id
        )

    @staticmethod
    def _has_newer_queued_offline_task(db, current_task: AsrTask) -> bool:
        """旧终稿每完成一片就礼让更新的下播场次，避免最新复盘等几十分钟。"""
        if get_dispatch_policy(db).order_mode == "fifo":
            return False
        current_session = db.get(LiveSession, current_task.session_id)
        if not current_session:
            return False
        current_start = current_session.live_start_time or datetime.min
        return (
            db.query(AsrTask.id)
            .join(LiveSession, LiveSession.id == AsrTask.session_id)
            .filter(
                AsrTask.id != current_task.id,
                AsrTask.task_type == "offline",
                AsrTask.status == TaskStatus.QUEUED,
                AsrTask.cancel_requested_at.is_(None),
                LiveSession.live_status != "live",
                or_(
                    LiveSession.live_start_time > current_start,
                    and_(
                        LiveSession.live_start_time == current_start,
                        LiveSession.id > current_session.id,
                    ),
                ),
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
        *,
        force_refresh: bool = False,
    ) -> tuple[str, StreamSource | None]:
        """
        转写前先探测 m3u8 是否有效；如果过期则调后端 API 自动刷新。

        返回: (最终可用的 m3u8_url, 关联的 StreamSource 或 None)
        """
        # ── 1. 快速探测 ──
        if force_refresh:
            health = {"alive": False, "error": "分片读取失败"}
            logger.warning("任务 %s: 分片取流失败，强制刷新回放地址", task.id)
        else:
            logger.info("任务 %s: 探测流地址可用性...", task.id)
            health = await probe_stream_url(m3u8_url, headers, probe_seconds=2.0)

            if health["alive"]:
                logger.info("任务 %s: 流地址有效，直接开始转写", task.id)
                return m3u8_url, db.get(
                    StreamSource, task.stream_id
                ) if task.stream_id else None

        logger.warning(
            "任务 %s: 流地址已过期（%s），尝试自动刷新...",
            task.id,
            health.get("error", "未知原因"),
        )

        # ── 2. 调后端 API 自动刷新 ──
        refresh_url = (
            f"{_BACKEND_BASE_URL}/live-sessions/{task.session_id}/refresh-stream"
        )
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
                            .order_by(
                                StreamSource.fetched_at.desc(), StreamSource.id.desc()
                            )
                            .first()
                        )
                        if new_source:
                            task.stream_id = new_source.id
                            db.commit()
                            return new_url, new_source
                        # 如果没找到新记录，直接用返回的 URL
                        return new_url, None
                    else:
                        logger.warning(
                            "任务 %s: 刷新 API 返回成功但无 stream_url", task.id
                        )
                else:
                    error_detail = "未知错误"
                    try:
                        error_detail = response.json().get(
                            "detail", response.text[:200]
                        )
                    except Exception:
                        error_detail = response.text[:200]
                    refresh_error_detail = sanitize_ffmpeg_error(
                        str(error_detail or "未知错误")
                    )[:300]
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
        return m3u8_url, db.get(
            StreamSource, task.stream_id
        ) if task.stream_id else None

    @staticmethod
    def _ensure_task_running(db, task: AsrTask) -> None:
        """每个安全检查点都读取停止标记，避免把用户停止误记成失败。"""
        db.refresh(task)
        if task.cancel_requested_at or task.status == TaskStatus.CANCELLED:
            raise TaskCancellationRequested(
                task.error_message or "用户已停止 ASR 转写，已完成分片会保留"
            )

    def _prepare_chunks(
        self,
        db,
        task: AsrTask,
        session: LiveSession,
        m3u8_url: str,
        *,
        live_buffer_start_seconds: float | None = None,
    ) -> list[AsrAudioChunk]:
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
            if live_buffer_start_seconds is not None:
                # 缓存从 Worker 接手直播的真实时刻开始。尚未成功的旧窗口若早于
                # 这个时刻，必须移动到缓存起点；中间缺口留给下播终稿补齐。
                for chunk in existing:
                    if (
                        chunk.status != TaskStatus.COMPLETED
                        and float(chunk.start_seconds or 0) < live_buffer_start_seconds
                    ):
                        chunk.start_seconds = live_buffer_start_seconds
                        chunk.end_seconds = (
                            live_buffer_start_seconds + settings.ASR_CHUNK_SECONDS
                        )
                        chunk.status = TaskStatus.PENDING
                        chunk.retry_count = 0
                        chunk.error_message = None
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
        if live_buffer_start_seconds is not None:
            ranges = [
                (
                    live_buffer_start_seconds,
                    live_buffer_start_seconds + settings.ASR_CHUNK_SECONDS,
                )
            ]
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
        publish_task_event(
            "asr",
            task,
            "chunks_created",
            {"chunk_count": len(chunks), "duration_seconds": duration},
        )
        return chunks

    @staticmethod
    async def _classify_chunk_failure(
        db,
        task: AsrTask,
        chunk: AsrAudioChunk,
        m3u8_url: str,
        headers: dict,
    ) -> str:
        """按分片起点探测回放，区分三种失败来源。

        返回：
            "skip"        — 分片起点已超出回放真实时长，该区间在回放中不存在；
            "slow_retry"  — 地址可拉且起点在回放时长内，但 fast-seek 定位读不到
                             音频（HLS 末尾定位越界），应改用 slow-seek 精确定位；
            "refresh"     — 地址失效或无法判断，走原有刷新逻辑。
        """
        try:
            health = await probe_stream_url(
                m3u8_url,
                headers,
                probe_seconds=2.0,
                start_seconds=float(chunk.start_seconds or 0),
            )
        except Exception as exc:
            logger.warning(
                "任务 %s 分片 %s 失败分类探测异常，按刷新处理: %s",
                task.id,
                chunk.chunk_index,
                exc,
            )
            return "refresh"

        duration_seconds = health.get("duration_seconds")
        start = float(chunk.start_seconds or 0)
        if duration_seconds is not None:
            # 起点已落在回放末尾之外（含 0.5 秒容差）：这块内容在回放中不存在，
            # 刷新地址也拿不到，直接跳过而不是继续消耗重试次数。
            if start >= float(duration_seconds) - 0.5:
                return "skip"
        if health.get("alive"):
            # 地址可拉且起点在回放时长内，但 fast-seek 读到 0 帧：
            # 属于 HLS 末尾定位问题，用 slow-seek 精确定位兜底。
            return "slow_retry"
        return "refresh"

    async def _process_chunk(
        self,
        db,
        task,
        chunk,
        m3u8_url,
        headers,
        *,
        is_live: bool = False,
        audio_buffer: LiveAudioBuffer | None = None,
        seek_mode: str = "fast",
    ) -> None:
        """执行单个真实音频分片；失败只回滚本分片的话术。"""
        client = FunasrClient()
        duration_seconds = (
            float(chunk.end_seconds - chunk.start_seconds)
            if chunk.end_seconds is not None
            else None
        )
        can_use_buffer = bool(
            audio_buffer
            and (
                (is_live and audio_buffer.is_running)
                or audio_buffer.covers_range(
                    float(chunk.start_seconds or 0),
                    float(chunk.end_seconds or chunk.start_seconds or 0),
                )
            )
        )
        if can_use_buffer:
            pipe = audio_buffer.pipe_for_range(
                float(chunk.start_seconds or 0),
                float(duration_seconds or settings.ASR_CHUNK_SECONDS),
            )
        else:
            pipe = M3u8Pipe(
                m3u8_url,
                headers,
                # 没有连续缓存的老任务保留兼容路径：实时流从当前点读取，
                # 已结束回放则按整场绝对时间定位。
                start_seconds=0 if is_live else chunk.start_seconds,
                duration_seconds=duration_seconds,
                # 分片快速定位失败后由上层切换为 slow-seek 精确定位重试。
                seek_mode=seek_mode,
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

            if self._should_yield_to_manual(db, task):
                raise _YieldToManualTask
            if (
                task.queue_source != "manual"
                and not is_live
                and self._has_queued_live_task(db, task.id)
            ):
                raise _YieldToLiveTask

            async with self._lane_coordinator.slot(task.task_type):
                try:
                    # 先确保 FunASR 容器在运行（挂了就自动重启）
                    await self._ensure_funasr_alive()
                    deadline = monotonic() + self._FUNASR_CONNECT_TIMEOUT
                    connected = await client.connect()
                    while not connected and monotonic() < deadline:
                        if self._should_yield_to_manual(db, task):
                            raise _YieldToManualTask
                        if (
                            task.queue_source != "manual"
                            and not is_live
                            and self._has_queued_live_task(db, task.id)
                        ):
                            raise _YieldToLiveTask
                        logger.info(
                            "任务 %s 分片 %s 等待 FunASR 模型就绪",
                            task.id,
                            chunk.chunk_index,
                        )
                        await asyncio.sleep(3)
                        connected = await client.connect()
                    if not connected and not settings.asr_mock_enabled:
                        raise RuntimeError(
                            f"FunASR 服务在 {self._FUNASR_CONNECT_TIMEOUT} 秒内未就绪，"
                            f"请检查容器日志: docker logs {self._FUNASR_CONTAINER}"
                        )

                    expected_timeout = int((duration_seconds or 0) * 2) + 120
                    timeout = max(
                        60, min(settings.ASR_TASK_TIMEOUT_SECONDS, expected_timeout)
                    )
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
        except _YieldToManualTask:
            # 人工任务到来时同样保留当前分片断点，不消耗一次重试。
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
                logger.warning(
                    "任务 %s 分片 %s 心跳更新失败: %s", task_id, chunk_id, exc
                )
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
        existing = (
            db.query(TranscriptFullText)
            .filter(TranscriptFullText.session_id == task.session_id)
            .first()
        )
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
        compliance_rules = load_enabled_compliance_rules(db)
        async for result in client.transcribe(
            task.session_id,
            pipe.read_frames(),
            task_type=task.task_type,
        ):
            self._ensure_task_running(db, task)
            absolute_result = dict(result)
            absolute_result["segment_start"] = offset + float(
                result.get("segment_start") or 0
            )
            absolute_result["segment_end"] = offset + float(
                result.get("segment_end") or 0
            )
            # 行业知识纠错：对 ASR 输出的原始文本做品牌名和术语校正
            raw_text = absolute_result.get("text", "")
            corrected_text = correct_asr_text(raw_text) if raw_text else ""
            absolute_result["text"] = corrected_text
            relative_words = result.get("word_timestamps") or []
            absolute_words = shift_word_timestamps(relative_words, offset)
            corrected_words, timestamp_source = remap_corrected_text(
                raw_text,
                corrected_text,
                absolute_words,
                str(result.get("timestamp_source") or "segment_estimated"),
            )
            absolute_result["word_timestamps"] = corrected_words
            absolute_result["timestamp_source"] = timestamp_source
            segment = TranscriptSegment(
                session_id=task.session_id,
                asr_chunk_id=chunk.id,
                segment_start=absolute_result["segment_start"],
                segment_end=absolute_result["segment_end"],
                text_content=corrected_text,
                raw_text_content=raw_text,
                word_timestamps_json=corrected_words or None,
                timestamp_source=timestamp_source,
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
                absolute_result.update(
                    {
                        "id": segment.id,
                        "session_id": task.session_id,
                        "text_content": corrected_text,
                        "segment_type": segment.segment_type,
                        "asr_status": segment.asr_status,
                        "ai_score": None,
                        "compliance_hits": match_compliance_text(
                            corrected_text, compliance_rules
                        ),
                    }
                )
                await ws_manager.publish_asr_result(task.session_id, absolute_result)

        return segment_count


async def main():
    worker = AsrWorker()

    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("收到停止信号，ASR Worker 关闭中...")
        write_asr_worker_heartbeat(worker._worker_id, status="stopping")
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
    try:
        await worker.shutdown()
        await ws_manager.close()
        logger.info("ASR Worker 已退出")
    finally:
        clear_asr_worker_heartbeat(os.getpid())


if __name__ == "__main__":
    asyncio.run(main())
