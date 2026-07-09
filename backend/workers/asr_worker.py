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
import signal
import sys
from datetime import datetime

from app.core.config import settings
from app.core.logger import logger
from app.core.database import SessionLocal, engine
from app.models.asr_tasks import AsrTask
from app.models.transcript_segments import TranscriptSegment
from app.models.transcript_full_texts import TranscriptFullText
from app.models.stream_sources import StreamSource
from app.services.asr.m3u8_pipe import M3u8Pipe
from app.services.asr.funasr_client import FunasrClient
from app.services.asr.websocket_manager import ws_manager


class AsrWorker:
    """ASR 转写 Worker"""

    def __init__(self):
        self._semaphore = asyncio.Semaphore(settings.MAX_REALTIME_ASR_TASKS or 1)
        self._running = False
        self._poll_interval = 5  # 秒

    async def run(self):
        """主循环"""
        self._running = True
        logger.info(f"ASR Worker 启动 (并发上限: {settings.MAX_REALTIME_ASR_TASKS})")

        while self._running:
            try:
                await self._poll_tasks()
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"ASR Worker 异常: {e}")
                await asyncio.sleep(10)

    async def _poll_tasks(self):
        """轮询 queued 任务"""
        db = SessionLocal()
        try:
            queued = (
                db.query(AsrTask)
                .filter(AsrTask.status == "queued")
                .order_by(AsrTask.created_at.asc())
                .limit(settings.ASR_MAX_QUEUED)
                .all()
            )

            for task in queued:
                if self._semaphore.locked():
                    break
                asyncio.create_task(self._process_task(task.id))
        finally:
            db.close()

    async def _process_task(self, task_id: int):
        """处理单个 ASR 任务"""
        async with self._semaphore:
            db = SessionLocal()
            try:
                task = db.query(AsrTask).get(task_id)
                if not task or task.status != "queued":
                    return

                task.status = "processing"
                task.started_at = datetime.utcnow()
                db.commit()

                # 获取流源
                stream = None
                if task.stream_id:
                    stream = db.query(StreamSource).get(task.stream_id)

                m3u8_url = stream.m3u8_url if stream else "https://mock.stream/live.m3u8"
                headers = dict(stream.headers_json) if stream and stream.headers_json else {}

                # ffmpeg pipe → FunASR → 存储
                pipe = M3u8Pipe(m3u8_url, headers)
                client = FunasrClient()

                if not await client.connect():
                    logger.info(f"任务 {task_id}: 使用 Mock ASR 模式")

                segment_count = 0
                async for result in client.transcribe(task.session_id, pipe.read_frames()):
                    # 写入 transcript_segments
                    segment = TranscriptSegment(
                        session_id=task.session_id,
                        segment_start=result.get("segment_start"),
                        segment_end=result.get("segment_end"),
                        text_content=result.get("text", ""),
                        asr_status="completed",
                        segment_type="asr_realtime",
                    )
                    db.add(segment)
                    db.commit()
                    segment_count += 1

                    # Redis Pub → WebSocket 推送
                    await ws_manager.publish_asr_result(task.session_id, result)

                # 拼接完整文本
                if segment_count > 0:
                    segments = (
                        db.query(TranscriptSegment)
                        .filter(TranscriptSegment.session_id == task.session_id)
                        .order_by(TranscriptSegment.segment_start.asc().nullslast())
                        .all()
                    )
                    full_text = "\n".join(
                        f"[{s.segment_start:.1f}s] {s.text_content}" for s in segments if s.text_content
                    )
                    existing = db.query(TranscriptFullText).filter(
                        TranscriptFullText.session_id == task.session_id
                    ).first()
                    if existing:
                        existing.full_text = full_text
                    else:
                        db.add(TranscriptFullText(session_id=task.session_id, full_text=full_text))
                    db.commit()

                task.status = "completed"
                task.completed_at = datetime.utcnow()
                db.commit()
                logger.info(f"任务 {task_id} 完成: {segment_count} 个片段")

                await pipe.close()
                await client.close()

            except Exception as e:
                logger.error(f"任务 {task_id} 失败: {e}")
                if db:
                    task = db.query(AsrTask).get(task_id)
                    if task:
                        task.status = "failed"
                        task.error_message = str(e)[:200]
                        db.commit()
            finally:
                db.close()


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
