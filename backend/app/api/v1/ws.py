"""Phase 5: WebSocket 转写 + REST 话术接口"""
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.transcript_segments import TranscriptSegment
from app.models.transcript_full_texts import TranscriptFullText
from app.models.live_sessions import LiveSession
from app.models.stream_sources import StreamSource
from app.models.asr_tasks import AsrTask
from app.services.asr.queue import queue_session_transcription
from app.services.asr.websocket_manager import ws_manager

# REST 路由（注册到 v1_router）
rest_router = APIRouter(prefix="/transcripts", tags=["话术转写"])


def build_full_transcript_text(segments: list[TranscriptSegment]) -> str:
    """从真实分段动态拼接全文，作为全文缓存尚未生成时的可靠兜底。"""
    return "\n".join(
        f"[{float(segment.segment_start or 0):.1f}s] {segment.text_content}"
        for segment in segments
        if segment.text_content
    )


def serialize_transcription_task(task: AsrTask, session: LiveSession, segment_count: int) -> dict:
    """统一任务明细结构，页面只展示数据库中的真实任务与场次信息。"""
    return {
        "id": task.id,
        "session_id": task.session_id,
        "status": task.status or "failed",
        "task_type": task.task_type or "offline",
        "anchor_name": session.anchor_name or "未知主播",
        "session_title": session.session_title or "未命名直播场次",
        "live_start_time": session.live_start_time,
        "live_duration_seconds": session.live_duration_seconds or 0,
        "segment_count": int(segment_count or 0),
        "error_message": task.error_message,
        "retry_count": task.retry_count or 0,
        "max_retries": task.max_retries or 0,
        "started_at": task.started_at,
        "completed_at": task.completed_at,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


@rest_router.post("/{session_id:int}/queue")
def queue_transcription(session_id: int, db: Session = Depends(get_db)):
    """为指定场次排队转写，复用已采集流源并避免重复任务。"""
    session = db.get(LiveSession, session_id)
    if not session:
        raise HTTPException(404, "直播场次不存在")

    try:
        task, created = queue_session_transcription(db, session)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.commit()
    db.refresh(task)
    return {"task_id": task.id, "status": task.status, "created": created}


@rest_router.post("/batch/queue-by-anchor")
def queue_transcription_by_anchor(
    per_anchor: int = Query(1, ge=1, le=3),
    min_duration_seconds: int = Query(600, ge=60, le=7200),
    db: Session = Depends(get_db),
):
    """每位主播增量选择较短的真实回放排队，默认每位一场。"""
    anchors = [
        row[0]
        for row in db.query(LiveSession.anchor_name)
        .filter(LiveSession.anchor_name.isnot(None), LiveSession.anchor_name != "")
        .distinct()
        .order_by(LiveSession.anchor_name.asc())
        .all()
    ]
    results = []
    created_count = 0
    for anchor in anchors:
        sessions = (
            db.query(LiveSession)
            .join(StreamSource, StreamSource.session_id == LiveSession.id)
            .filter(
                LiveSession.anchor_name == anchor,
                LiveSession.live_duration_seconds >= min_duration_seconds,
                StreamSource.status == "active",
            )
            .order_by(LiveSession.live_duration_seconds.asc(), LiveSession.live_start_time.desc())
            .all()
        )
        selected = 0
        for session in sessions:
            latest_task = (
                db.query(AsrTask)
                .filter(AsrTask.session_id == session.id)
                .order_by(AsrTask.created_at.desc(), AsrTask.id.desc())
                .first()
            )
            # 批量增量不反复消耗已确认无语音/失效的回放；单场接口仍可人工重试。
            if latest_task and latest_task.status == "failed":
                continue
            task, created = queue_session_transcription(db, session)
            if task.status == "completed":
                continue
            results.append({
                "anchor_name": anchor,
                "session_id": session.id,
                "duration_seconds": session.live_duration_seconds,
                "task_id": task.id,
                "status": task.status,
                "created": created,
            })
            created_count += int(created)
            selected += 1
            if selected >= per_anchor:
                break

    db.commit()
    return {
        "anchor_count": len(anchors),
        "selected_count": len(results),
        "created_count": created_count,
        "tasks": results,
    }


@rest_router.get("/tasks/status")
def get_transcription_task_status(db: Session = Depends(get_db)):
    """返回话术任务汇总，供页面显示真实排队进度。"""
    counts = {"queued": 0, "processing": 0, "completed": 0, "failed": 0}
    for status, count in db.query(AsrTask.status, func.count(AsrTask.id)).group_by(AsrTask.status):
        counts[status or "failed"] = count
    return counts


@rest_router.get("/tasks")
def list_transcription_tasks(
    status: str | None = Query(None, pattern="^(queued|processing|completed|failed)$"),
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """返回近期任务明细，支持从状态卡片穿透查看真实失败原因。"""
    segment_counts = (
        db.query(
            TranscriptSegment.session_id.label("session_id"),
            func.count(TranscriptSegment.id).label("segment_count"),
        )
        .group_by(TranscriptSegment.session_id)
        .subquery()
    )
    query = (
        db.query(
            AsrTask,
            LiveSession,
            func.coalesce(segment_counts.c.segment_count, 0).label("segment_count"),
        )
        .join(LiveSession, LiveSession.id == AsrTask.session_id)
        .outerjoin(segment_counts, segment_counts.c.session_id == AsrTask.session_id)
    )
    if status:
        query = query.filter(AsrTask.status == status)
    rows = query.order_by(AsrTask.id.desc()).limit(limit).all()
    return [serialize_transcription_task(task, session, segment_count) for task, session, segment_count in rows]


@rest_router.get("/{session_id:int}/segments")
def list_transcript_segments(
    session_id: int,
    limit: int = Query(200, le=500),
    db: Session = Depends(get_db),
):
    """获取某场直播的话术分段列表"""
    segments = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.session_id == session_id)
        .order_by(TranscriptSegment.segment_start.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": s.id,
            "segment_start": float(s.segment_start) if s.segment_start else 0,
            "segment_end": float(s.segment_end) if s.segment_end else 0,
            "text_content": s.text_content or "",
            "segment_type": s.segment_type or "",
            "asr_status": s.asr_status or "pending",
            "ai_score": float(s.ai_score) if s.ai_score else None,
        }
        for s in segments
    ]


@rest_router.get("/{session_id:int}/full-text")
def get_full_text(session_id: int, db: Session = Depends(get_db)):
    """获取某场直播的完整话术文本"""
    record = (
        db.query(TranscriptFullText)
        .filter(TranscriptFullText.session_id == session_id)
        .first()
    )
    if not record:
        segments = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.session_id == session_id)
            .order_by(TranscriptSegment.segment_start.asc(), TranscriptSegment.id.asc())
            .limit(5000)
            .all()
        )
        full_text = build_full_transcript_text(segments)
        # 未开始或失败场次没有缓存全文是正常状态；已有分段时仍返回完整可读内容。
        return {"id": None, "full_text": full_text, "available": bool(full_text)}
    return {"id": record.id, "full_text": record.full_text or "", "available": bool(record.full_text)}


# WebSocket 路由（直接在 app 上注册）
# 在 main.py 中注册: app.websocket("/ws/transcript/{session_id}")(transcript_ws)


async def transcript_ws(websocket: WebSocket):
    """前端 WebSocket 连接，实时接收 ASR 转写结果"""
    session_id = int(websocket.path_params["session_id"])
    await websocket.accept()
    await ws_manager.connect(session_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(session_id, websocket)
