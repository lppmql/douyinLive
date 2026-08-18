"""ASR 单任务停止、重试与人工优先控制，供多个 API 页面共用。"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.status import TaskStatus
from app.models.asr_tasks import AsrTask
from app.models.live_sessions import LiveSession
from app.services.asr.queue import queue_session_transcription
from app.services.tasks.runtime import publish_task_event, touch_task


def request_stop_asr_task(db: Session, task_id: int) -> AsrTask:
    """安全停止排队或处理中任务；处理中任务在当前音频安全点退出。"""
    task = db.get(AsrTask, task_id)
    if not task:
        raise LookupError("ASR 任务不存在")
    now = datetime.utcnow()
    if task.status == TaskStatus.QUEUED:
        task.status = TaskStatus.CANCELLED
        task.cancel_requested_at = now
        task.completed_at = now
        task.error_message = "用户在执行前停止任务，已保留完成分片"
    elif task.status == TaskStatus.PROCESSING:
        task.cancel_requested_at = now
        task.error_message = "正在等待当前音频处理安全点后停止"
    else:
        raise ValueError("只有排队中或转写中的任务可以停止")
    touch_task(task)
    db.commit()
    publish_task_event("asr", task, "cancel_requested", {})
    return task


def retry_asr_task(db: Session, task_id: int) -> AsrTask:
    """从失败或暂停任务的已完成分片之后继续，恢复为普通自动任务。"""
    task = db.get(AsrTask, task_id)
    if not task:
        raise LookupError("ASR 任务不存在")
    if task.status not in (TaskStatus.FAILED, TaskStatus.CANCELLED):
        raise ValueError("只有失败或已停止的 ASR 任务可以重试")
    session = db.get(LiveSession, task.session_id)
    if not session:
        raise LookupError("ASR 任务关联的直播场次不存在")
    retried_task, _created = queue_session_transcription(
        db, session, queue_source="auto"
    )
    db.commit()
    publish_task_event(
        "asr", retried_task, "retried", {"session_id": session.id}
    )
    return retried_task


def release_manual_priority(db: Session, task_id: int) -> AsrTask:
    """取消人工独占但保留任务和断点，让它重新参加自动排序。"""
    task = db.get(AsrTask, task_id)
    if not task:
        raise LookupError("ASR 任务不存在")
    if task.queue_source != "manual" or task.status not in {
        TaskStatus.QUEUED,
        TaskStatus.PROCESSING,
    }:
        raise ValueError("该任务当前不是人工优先任务")
    task.queue_source = "auto"
    task.priority = 50
    task.error_message = "已取消人工优先，任务按自动排序继续"
    touch_task(task)
    db.commit()
    publish_task_event("asr", task, "manual_priority_released", {})
    return task
