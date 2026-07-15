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
from datetime import datetime

from app.core.config import settings
from app.core.logger import logger
from app.core.database import SessionLocal, engine
from app.models.asr_tasks import AsrTask
from app.models.asr_audio_chunks import AsrAudioChunk
from app.models.transcript_segments import TranscriptSegment
from app.models.transcript_full_texts import TranscriptFullText
from app.models.stream_sources import StreamSource
from app.models.live_sessions import LiveSession
from app.services.asr.m3u8_pipe import M3u8Pipe
from app.services.asr.funasr_client import FunasrClient
from app.services.asr.websocket_manager import ws_manager
from app.services.ai.scoring import score_session_transcript
from app.services.ai.kb_service import sync_session_to_kb
from app.services.sync import sync_session
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


class AsrWorker:
    """ASR 转写 Worker"""

    def __init__(self):
        self._semaphore = asyncio.Semaphore(settings.MAX_REALTIME_ASR_TASKS or 1)
        self._active_tasks: set[asyncio.Task] = set()
        self._running = False
        self._poll_interval = 5  # 秒
        self._worker_id = current_worker_id("asr")

    async def run(self):
        """主循环"""
        self._running = True
        logger.info(f"ASR Worker 启动 (并发上限: {settings.MAX_REALTIME_ASR_TASKS})")
        self._recover_stale_tasks()

        while self._running:
            try:
                await self._poll_tasks()
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"ASR Worker 异常: {e}")
                await asyncio.sleep(10)

    def _recover_stale_tasks(self):
        """Worker 重启时保留已完成分片，并重新排队未完成任务。"""
        db = SessionLocal()
        try:
            stale = db.query(AsrTask).filter(AsrTask.status == "processing").all()
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
        finally:
            db.close()

    async def _poll_tasks(self):
        """轮询 queued 任务"""
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
                worker_task.add_done_callback(self._active_tasks.discard)
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
                touch_task(task, self._worker_id)
                db.commit()
                publish_task_event("asr", task, "completed", {"segment_count": segment_count, "chunk_count": len(chunks)})
                logger.info("任务 %s 完成: %s 个分片，%s 个话术片段", task_id, len(chunks), segment_count)

                # ASR 成功后自动完成 AI 评分和知识库同步；AI 失败不回滚真实话术。
                try:
                    score = score_session_transcript(task.session_id, db)
                    knowledge_saved = sync_session_to_kb(db, task.session_id)
                    sync_session(db, task.session_id)
                    logger.info(
                        "任务 %s AI/DataEase 闭环完成: score=%s, knowledge=%s",
                        task_id,
                        (score or {}).get("total_score"),
                        knowledge_saved,
                    )
                except Exception as ai_exc:
                    logger.exception("任务 %s AI 分析或知识库同步失败: %s", task_id, ai_exc)

            except Exception as exc:
                logger.error("任务 %s 失败: %s", task_id, exc)
                task = db.get(AsrTask, task_id)
                if task:
                    task.status = "failed"
                    task.error_message = str(exc)[:500]
                    task.completed_at = datetime.utcnow()
                    touch_task(task, self._worker_id)
                    db.commit()
                    publish_task_event("asr", task, "failed", {"error": task.error_message})
            finally:
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

    def _save_full_text(self, db, task: AsrTask, chunks: list[AsrAudioChunk]) -> None:
        """只使用当前任务分片生成完整话术，避免跨任务重复拼接。"""
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
        db.commit()

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
