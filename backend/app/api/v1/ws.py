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
