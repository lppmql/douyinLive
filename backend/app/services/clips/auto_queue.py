"""离线终稿完成后的自动剪辑排队入口。"""

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logger import logger
from app.models.clip_clips import ClipClip
from app.models.stream_sources import StreamSource


def queue_clip_after_offline_final(
    session_id: int,
    *,
    asr_task_id: int | None = None,
) -> bool:
    """为刚完成的离线终稿排队剪辑，失败时不回滚已完成的 ASR 任务。

    该函数只由 ASR 离线终稿的完成事件调用，不扫描历史场次。任务控制器还会
    对同一场次的待执行/执行中剪辑任务做幂等去重，防止 Worker 重试重复排队。
    """
    if not settings.CLIP_AUTO_GENERATE:
        return False

    db = SessionLocal()
    try:
        has_source = (
            db.query(StreamSource.id)
            .filter(StreamSource.session_id == session_id)
            .first()
            is not None
        )
        if not has_source:
            logger.info("场次 %s 无真实回放流源，跳过自动剪辑", session_id)
            return False

        has_current_clip = (
            db.query(ClipClip.id)
            .filter(
                ClipClip.session_id == session_id,
                ClipClip.status.in_(["draft", "approved"]),
            )
            .first()
            is not None
        )
        if has_current_clip:
            logger.info("场次 %s 已有待确认或已通过成片，跳过自动剪辑", session_id)
            return False

        from app.services.tasks.control import collector_task_control

        task, created = collector_task_control.enqueue(
            "clip",
            {
                "session_id": session_id,
                "trigger": "offline_final",
                "asr_task_id": asr_task_id,
            },
        )
        if created:
            logger.info(
                "新离线终稿已排队自动剪辑 session=%s asr_task=%s clip_task=%s",
                session_id,
                asr_task_id,
                task.id,
            )
        return created
    except Exception as exc:  # noqa: BLE001 - 排队失败不得污染已经完成的终稿
        logger.warning(
            "新离线终稿自动剪辑排队失败 session=%s asr_task=%s: %s",
            session_id,
            asr_task_id,
            exc,
        )
        return False
    finally:
        db.close()
