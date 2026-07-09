"""Phase 5: WebSocket 转写 + REST 话术接口"""
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.transcript_segments import TranscriptSegment
from app.models.transcript_full_texts import TranscriptFullText
from app.services.asr.websocket_manager import ws_manager

# REST 路由（注册到 v1_router）
rest_router = APIRouter(prefix="/transcripts", tags=["话术转写"])


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


async def transcript_ws(websocket: WebSocket, session_id: int):
    """前端 WebSocket 连接，实时接收 ASR 转写结果"""
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
