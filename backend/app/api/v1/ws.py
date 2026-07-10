"""Phase 5: WebSocket 转写 + REST 话术接口"""
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.transcript_segments import TranscriptSegment
from app.models.transcript_full_texts import TranscriptFullText
from app.models.live_sessions import LiveSession
from app.models.stream_sources import StreamSource
from app.models.asr_tasks import AsrTask
from app.services.asr.websocket_manager import ws_manager
from datetime import datetime

# REST 路由（注册到 v1_router）
rest_router = APIRouter(prefix="/transcripts", tags=["话术转写"])


@rest_router.post("/{session_id}/queue")
def queue_transcription(session_id: int, db: Session = Depends(get_db)):
    """为指定场次排队转写，复用已采集流源并避免重复任务。"""
    session = db.query(LiveSession).get(session_id)
    if not session:
        raise HTTPException(404, "直播场次不存在")

    stream = (
        db.query(StreamSource)
        .filter(StreamSource.session_id == session_id, StreamSource.status == "active")
        .order_by(StreamSource.fetched_at.desc(), StreamSource.id.desc())
        .first()
    )
    if not stream and session.stream_url:
        stream = StreamSource(
            session_id=session_id,
            m3u8_url=session.stream_url[:2000],
            headers_json={"Referer": session.dashboard_url or ""},
            status="active",
            fetched_at=datetime.utcnow(),
        )
        db.add(stream)
        db.flush()
    if not stream:
        raise HTTPException(400, "该场次暂无可用直播流，请先重新采集流地址")

    existing = (
        db.query(AsrTask)
        .filter(AsrTask.session_id == session_id, AsrTask.status.in_(["queued", "processing"]))
        .order_by(AsrTask.created_at.desc())
        .first()
    )
    if existing:
        return {"task_id": existing.id, "status": existing.status, "created": False}

    task = AsrTask(session_id=session_id, stream_id=stream.id, status="queued", task_type="offline")
    db.add(task)
    db.commit()
    db.refresh(task)
    return {"task_id": task.id, "status": task.status, "created": True}


@rest_router.get("/{session_id}/segments")
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


@rest_router.get("/{session_id}/full-text")
def get_full_text(session_id: int, db: Session = Depends(get_db)):
    """获取某场直播的完整话术文本"""
    record = (
        db.query(TranscriptFullText)
        .filter(TranscriptFullText.session_id == session_id)
        .first()
    )
    if not record:
        raise HTTPException(404, "完整话术不存在")
    return {"id": record.id, "full_text": record.full_text or ""}


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
