"""
ASR Worker 进程 — 独立运行的话术转写服务

从 DB 轮询 asr_tasks，通过 ffmpeg pipe 拉流 → FunASR 识别 → 写入 transcript_segments

启动:
    cd backend && source .venv/bin/activate
    python -m workers.asr_worker

环境变量:
    ASR_WORKER_MODE=true
    MAX_REALTIME_ASR_TASKS=1
"""
import asyncio
import hashlib
import signal
import sys
from time import monotonic
from datetime import datetime, timedelta

from sqlalchemy.exc import DataError

from app.core.config import settings
from app.core.logger import logger
from app.core.database import SessionLocal, engine
from app.models.asr_tasks import AsrTask
from app.models.asr_audio_chunks import AsrAudioChunk
from app.models.transcript_segments import TranscriptSegment
from app.models.transcript_full_texts import TranscriptFullText
from app.models.stream_sources import StreamSource
from app.models.live_sessions import LiveSession
from app.models.scraper_logs import ScraperLog
from app.services.asr.m3u8_pipe import M3u8Pipe
from app.services.asr.funasr_client import FunasrClient
from app.services.asr.queue import queue_auto_transcriptions
from app.services.asr.websocket_manager import ws_manager
from app.services.ai.post_collection import process_session_post_collection
from app.services.tasks.runtime import (
    current_worker_id,
    ensure_task_identity,
    publish_task_event,
    touch_task,
)


def build_chunk_ranges(duration_seconds: int, chunk_seconds: int) -> list[tuple[float, float | None]]:
    """按场次时长生成连续、不重叠的音频分片范围。"""
    duration = max(0, int(duration_seconds or 0))
    size = max(60, int(chunk_seconds or 0))
    if duration == 0:
        return [(0.0, None)]
    return [
        (float(start), float(min(duration, start + size)))
        for start in range(0, duration, size)
    ]


def is_full_text_too_long_error(exc: DataError) -> bool:
    """识别迁移前 MySQL TEXT 容量不足错误。"""
    return bool(getattr(exc, "orig", None) and getattr(exc.orig, "args", ()) and exc.orig.args[0] == 1406)


class AsrWorker:
    """ASR 转写 Worker"""

    def __init__(self):
        self._semaphore = asyncio.Semaphore(settings.MAX_REALTIME_ASR_TASKS or 1)
        self._active_tasks: set[asyncio.Task] = set()
        self._active_task_ids: set[int] = set()
        self._active_postprocess_tasks: set[asyncio.Task] = set()
        self._active_postprocess_ids: set[int] = set()
        self._running = False
        self._poll_interval = 5  # 秒
        self._worker_id = current_worker_id("asr")

    async def run(self):
        """主循环"""
        self._running = True
        logger.info(f"ASR Worker 启动 (并发上限: {settings.MAX_REALTIME_ASR_TASKS})")
        self._recover_stale_tasks(recover_all=True)

        while self._running:
            try:
                await self._poll_tasks()
                await self._poll_postprocess_tasks()
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
                can_retry = (task.retry_count or 0) < (task.max_retries or 3)
                task.status = "queued" if can_retry else "failed"
                task.error_message = (
                    "Worker 重启，已保留完成分片并从断点继续"
                    if can_retry
                    else "Worker 重启时任务已达到最大执行次数"
                )
                task.completed_at = None if can_retry else datetime.utcnow()
                touch_task(task)
                chunks = db.query(AsrAudioChunk).filter(
                    AsrAudioChunk.task_id == task.id,
                    AsrAudioChunk.status == "processing",
                ).all()
                for chunk in chunks:
                    chunk.status = "pending" if chunk.retry_count < chunk.max_retries else "failed"
                    chunk.error_message = "Worker 重启，分片等待断点续传"
                    chunk.heartbeat_at = datetime.utcnow()
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
        max_tasks = settings.MAX_REALTIME_ASR_TASKS or 1
        available_slots = max(0, max_tasks - len(self._active_tasks))
        if available_slots == 0:
            return

        db = SessionLocal()
        try:
            queued_ids = [row[0] for row in (
                db.query(AsrTask)
                .join(LiveSession, LiveSession.id == AsrTask.session_id)
                .filter(AsrTask.status == "queued")
                .with_entities(AsrTask.id)
                .order_by(AsrTask.priority.asc(), LiveSession.live_duration_seconds.asc(), AsrTask.created_at.asc())
                .limit(min(settings.ASR_MAX_QUEUED, available_slots))
                .all()
            )]

            for task_id in queued_ids:
                now = datetime.utcnow()
                claimed = db.query(AsrTask).filter(
                    AsrTask.id == task_id,
                    AsrTask.status == "queued",
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
                ensure_task_identity(task, "asr", f"asr:session:{task.session_id}")
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

                m3u8_url = stream.m3u8_url
                headers = dict(stream.headers_json) if stream and stream.headers_json else {}
                chunks = self._prepare_chunks(db, task, session, m3u8_url)

                for chunk in chunks:
                    if chunk.status == "completed":
                        continue
                    while chunk.status != "completed" and chunk.retry_count < chunk.max_retries:
                        await self._process_chunk(db, task, chunk, m3u8_url, headers)
                        db.refresh(chunk)
                    if chunk.status != "completed":
                        raise RuntimeError(
                            f"音频分片 {chunk.chunk_index + 1}/{len(chunks)} 达到最大重试次数: "
                            f"{chunk.error_message or '未知错误'}"
                        )

                segment_count = sum(int(chunk.segment_count or 0) for chunk in chunks)
                if segment_count == 0:
                    raise RuntimeError("全部真实音频分片均未识别到有效话术，直播流可能已过期或没有人声")

                self._save_full_text(db, task, chunks)
                task.status = "completed"
                task.error_message = None
                task.completed_at = datetime.utcnow()
                task.postprocess_status = "pending"
                task.postprocess_started_at = None
                task.postprocess_completed_at = None
                task.postprocess_error = None
                task.postprocess_attempt_count = 0
                task.postprocess_result = None
                touch_task(task, self._worker_id)
                db.commit()
                publish_task_event("asr", task, "completed", {"segment_count": segment_count, "chunk_count": len(chunks)})
                logger.info("任务 %s 完成: %s 个分片，%s 个话术片段", task_id, len(chunks), segment_count)

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
                        touch_task(task, self._worker_id)
                        db.commit()
                        publish_task_event("asr", task, "failed", {"error": task.error_message})
                except Exception as persist_exc:
                    db.rollback()
                    logger.exception("任务 %s 失败状态保存异常: %s", task_id, persist_exc)
            finally:
                try:
                    queue_auto_transcriptions(db, limit=1)
                except Exception as queue_exc:
                    db.rollback()
                    logger.warning("任务 %s 完成后补充 ASR 队列失败: %s", task_id, queue_exc)
                db.close()

    def _prepare_chunks(self, db, task: AsrTask, session: LiveSession, m3u8_url: str) -> list[AsrAudioChunk]:
        """按真实场次时长幂等创建分片，首次切换时清理旧的无分片中间产物。"""
        existing = (
            db.query(AsrAudioChunk)
            .filter(AsrAudioChunk.task_id == task.id)
            .order_by(AsrAudioChunk.chunk_index.asc())
            .all()
        )
        if existing:
            return existing

        db.query(TranscriptSegment).filter(
            TranscriptSegment.session_id == task.session_id,
            TranscriptSegment.asr_chunk_id.is_(None),
            TranscriptSegment.segment_type.in_(["asr_realtime", "asr_offline"]),
        ).delete(synchronize_session=False)
        db.query(TranscriptFullText).filter(
            TranscriptFullText.session_id == task.session_id
        ).delete(synchronize_session=False)

        duration = max(0, int(session.live_duration_seconds or 0))
        ranges = build_chunk_ranges(duration, settings.ASR_CHUNK_SECONDS)
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

    async def _process_chunk(self, db, task, chunk, m3u8_url, headers) -> None:
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
            start_seconds=chunk.start_seconds,
            duration_seconds=duration_seconds,
        )
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

            deadline = monotonic() + settings.ASR_ENGINE_READY_TIMEOUT_SECONDS
            connected = await client.connect()
            while not connected and monotonic() < deadline:
                logger.info("任务 %s 分片 %s 等待 FunASR 模型就绪", task.id, chunk.chunk_index)
                await asyncio.sleep(5)
                connected = await client.connect()
            if not connected and not settings.asr_mock_enabled:
                raise RuntimeError(
                    f"真实 FunASR 服务在 {settings.ASR_ENGINE_READY_TIMEOUT_SECONDS} 秒内未就绪"
                )

            timeout = max(
                settings.ASR_TASK_TIMEOUT_SECONDS,
                int((duration_seconds or 0) * 1.5) + 120,
            )
            segment_count = await asyncio.wait_for(
                self._consume_transcription(db, task, chunk, client, pipe),
                timeout=timeout,
            )
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
        except Exception as exc:
            # 分片写入若触发数据库异常，先恢复事务再保存可重试状态。
            db.rollback()
            chunk = db.get(AsrAudioChunk, chunk.id)
            task = db.get(AsrTask, task.id)
            if not chunk or not task:
                raise
            chunk.status = "failed"
            chunk.error_message = str(exc)[:500]
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
            await pipe.close()
            await client.close()

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
        async for result in client.transcribe(task.session_id, pipe.read_frames()):
            absolute_result = dict(result)
            absolute_result["segment_start"] = offset + float(result.get("segment_start") or 0)
            absolute_result["segment_end"] = offset + float(result.get("segment_end") or 0)
            segment = TranscriptSegment(
                session_id=task.session_id,
                asr_chunk_id=chunk.id,
                segment_start=absolute_result["segment_start"],
                segment_end=absolute_result["segment_end"],
                text_content=absolute_result.get("text", ""),
                asr_status="completed",
                segment_type="asr_offline" if task.task_type == "offline" else "asr_realtime",
            )
            db.add(segment)
            chunk.segment_count = segment_count + 1
            chunk.heartbeat_at = datetime.utcnow()
            touch_task(task, self._worker_id)
            db.commit()
            segment_count += 1
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
