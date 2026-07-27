"""Phase 5: WebSocket 转写 + REST 话术接口"""
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.core.security import MEDIA_ACCESS_COOKIE, decode_token
from app.models.transcript_segments import TranscriptSegment
from app.models.transcript_full_texts import TranscriptFullText
from app.models.live_sessions import LiveSession
from app.models.stream_sources import StreamSource
from app.models.asr_audio_chunks import AsrAudioChunk
from app.core.status import TaskStatus
from app.models.asr_tasks import AsrTask
from app.models.user import User
from app.services.asr.queue import queue_session_transcription
from app.services.asr.websocket_manager import ws_manager
from app.schemas.transcript import (
    TranscriptQueueResponse,
    TranscriptBatchResponse,
    TranscriptTaskStatusResponse,
    TranscriptTaskOut,
    TranscriptSegmentOut,
    TranscriptFullTextResponse,
    TranscriptTaskDeleteResponse,
    TranscriptFailedClearResponse,
)

# REST 路由（注册到 v1_router）
rest_router = APIRouter(prefix="/transcripts", tags=["话术转写"])


def build_full_transcript_text(segments: list[TranscriptSegment]) -> str:
    """从真实分段动态拼接全文，作为全文缓存尚未生成时的可靠兜底。"""
    return "\n".join(
        f"[{float(segment.segment_start or 0):.1f}s] {segment.text_content}"
        for segment in segments
        if segment.text_content
    )


def get_chunk_counts(db: Session, task_ids: list[int]) -> dict[int, tuple[int, int]]:
    """批量查询每个任务的分片总数和已完成数（用于显示转写进度）。

    每个 ASR 任务会被拆成多个音频分片（asr_audio_chunks），Worker 逐个处理。
    进度 = 已完成分片数 / 总分数。
    """
    from collections import defaultdict

    counts: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    if not task_ids:
        return {}
    rows = (
        db.query(AsrAudioChunk.task_id, AsrAudioChunk.status, func.count(AsrAudioChunk.id))
        .filter(AsrAudioChunk.task_id.in_(task_ids))
        .group_by(AsrAudioChunk.task_id, AsrAudioChunk.status)
        .all()
    )
    for task_id, status, count in rows:
        counts[task_id][0] += int(count or 0)
        if status in {TaskStatus.COMPLETED, TaskStatus.SKIPPED}:
            counts[task_id][1] += int(count or 0)
    return {task_id: (values[0], values[1]) for task_id, values in counts.items()}


def serialize_transcription_task(
    task: AsrTask,
    session: LiveSession,
    segment_count: int,
    chunk_counts: tuple[int, int] = (0, 0),
) -> dict:
    """统一任务明细结构，页面只展示数据库中的真实任务与场次信息。

    chunk_counts: (total_chunks, completed_chunks)，用于前端显示转写进度条。
    """
    total_chunks, completed_chunks = chunk_counts
    progress_percent = (
        100 if task.status == TaskStatus.COMPLETED
        else int(completed_chunks / total_chunks * 100) if total_chunks
        else 0
    )
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
        "postprocess_status": getattr(task, "postprocess_status", None) or TaskStatus.PENDING,
        "postprocess_error": getattr(task, "postprocess_error", None),
        "postprocess_result": getattr(task, "postprocess_result", None),
        "postprocess_attempt_count": getattr(task, "postprocess_attempt_count", 0) or 0,
        "postprocess_started_at": getattr(task, "postprocess_started_at", None),
        "postprocess_completed_at": getattr(task, "postprocess_completed_at", None),
        "retry_count": task.retry_count or 0,
        "max_retries": task.max_retries or 0,
        "started_at": task.started_at,
        "completed_at": task.completed_at,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        # 转写进度（音频分片维度）
        "total_chunks": total_chunks,
        "completed_chunks": completed_chunks,
        "progress_percent": progress_percent,
    }


@rest_router.post("/{session_id:int}/queue", response_model=TranscriptQueueResponse)
def queue_transcription(session_id: int, db: Session = Depends(get_db)):
    """为指定场次排队转写，复用已采集流源并避免重复任务。

    如果 ASR Worker 未运行（比如之前在采集页关闭了 ASR），自动拉起运行时，
    避免任务创建后无人处理一直卡在 queued 状态。
    """
    session = db.get(LiveSession, session_id)
    if not session:
        raise HTTPException(404, "直播场次不存在")

    try:
        task, created = queue_session_transcription(db, session)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.commit()
    db.refresh(task)

    # 确保 ASR 运行时在跑（已运行时 start_asr_runtime 是幂等的，不会重复启动）
    from app.services.asr.control import start_asr_runtime
    start_asr_runtime()

    return {"task_id": task.id, "status": task.status, "created": created}


@rest_router.post("/batch/queue-by-anchor", response_model=TranscriptBatchResponse)
def queue_transcription_by_anchor(
    per_anchor: int = Query(1, ge=1, le=3),
    min_duration_seconds: int = Query(600, ge=60, le=7200),
    db: Session = Depends(get_db),
):
    """每位主播从最新真实回放开始增量排队，默认每位一场。"""
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
            .order_by(LiveSession.live_start_time.desc(), LiveSession.id.desc())
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

    # 确保 ASR 运行时在跑（比如之前在采集页关闭了 ASR，批量排队后需要 Worker 来处理）
    from app.services.asr.control import start_asr_runtime
    start_asr_runtime()

    return {
        "anchor_count": len(anchors),
        "selected_count": len(results),
        "created_count": created_count,
        "tasks": results,
    }


@rest_router.get("/tasks/status", response_model=TranscriptTaskStatusResponse)
def get_transcription_task_status(db: Session = Depends(get_db)):
    """返回话术任务汇总，供页面显示真实排队进度。"""
    counts = {TaskStatus.QUEUED: 0, "processing": 0, "completed": 0, "failed": 0}
    for status, count in db.query(AsrTask.status, func.count(AsrTask.id)).group_by(AsrTask.status):
        counts[status or "failed"] = count
    return counts


@rest_router.get("/tasks", response_model=list[TranscriptTaskOut])
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
    rows = (
        query.order_by(
            LiveSession.live_start_time.desc(),
            LiveSession.id.desc(),
            AsrTask.id.desc(),
        )
        .limit(limit)
        .all()
    )
    # 批量查询分片进度（一次 SQL 查所有任务的分片数，避免 N+1 问题）
    task_ids = [task.id for task, _, _ in rows]
    chunk_counts_map = get_chunk_counts(db, task_ids)
    return [
        serialize_transcription_task(
            task, session, segment_count,
            chunk_counts=chunk_counts_map.get(task.id, (0, 0)),
        )
        for task, session, segment_count in rows
    ]


@rest_router.delete("/tasks/failed", response_model=TranscriptFailedClearResponse)
def clear_failed_transcription_tasks(db: Session = Depends(get_db)):
    """一键清空全部失败和已取消的转写任务，同时清理关联的音频分片和话术分段。

    只允许删除 failed / cancelled 状态的任务，防止误删正常任务。
    """
    allowed_statuses = [TaskStatus.FAILED, TaskStatus.CANCELLED]
    failed_tasks = db.query(AsrTask).filter(AsrTask.status.in_(allowed_statuses)).all()

    if not failed_tasks:
        return {"deleted_count": 0, "message": "没有需要清理的失败任务"}

    task_ids = [t.id for t in failed_tasks]
    session_ids = list({t.session_id for t in failed_tasks})

    # ⚠️ 外键依赖链：transcript_segments.asr_chunk_id → asr_audio_chunks.id → asr_tasks.id
    # 必须按「孙子→儿子→爷爷」顺序删，否则 MySQL 外键约束报错
    # 1. 先删话术分段（引用 asr_audio_chunks）
    db.query(TranscriptSegment).filter(
        TranscriptSegment.session_id.in_(session_ids)
    ).delete(synchronize_session=False)

    # 2. 再删音频分片（引用 asr_tasks）
    db.query(AsrAudioChunk).filter(AsrAudioChunk.task_id.in_(task_ids)).delete(synchronize_session=False)

    # 3. 最后删失败任务本身
    deleted = db.query(AsrTask).filter(AsrTask.id.in_(task_ids)).delete(synchronize_session=False)

    db.commit()
    return {"deleted_count": deleted, "message": f"已清理 {deleted} 条失败任务及关联数据"}


@rest_router.delete("/tasks/{task_id:int}", response_model=TranscriptTaskDeleteResponse)
def delete_transcription_task(task_id: int, db: Session = Depends(get_db)):
    """删除单条转写任务（仅限 failed / cancelled 状态），同时清理关联的音频分片。"""
    task = db.get(AsrTask, task_id)
    if not task:
        raise HTTPException(404, f"任务 #{task_id} 不存在")

    if task.status not in {TaskStatus.FAILED, TaskStatus.CANCELLED}:
        raise HTTPException(
            400,
            f"任务 #{task_id} 当前状态为「{task.status}」，仅允许删除失败或已取消的任务。"
            f"如需停止正在进行的任务，请先调用停止接口。",
        )

    # ⚠️ 外键依赖链：transcript_segments.asr_chunk_id → asr_audio_chunks.id → asr_tasks.id
    # 必须按「孙子→儿子→爷爷」顺序删
    # 1. 先删话术分段（引用 asr_audio_chunks）
    db.query(TranscriptSegment).filter(
        TranscriptSegment.session_id == task.session_id
    ).delete(synchronize_session=False)

    # 2. 再删音频分片（引用 asr_tasks）
    db.query(AsrAudioChunk).filter(AsrAudioChunk.task_id == task_id).delete(synchronize_session=False)

    # 3. 最后删任务本身
    db.delete(task)
    db.commit()

    return {"task_id": task_id, "deleted": True, "message": f"任务 #{task_id} 已删除"}


@rest_router.get("/{session_id:int}/segments", response_model=list[TranscriptSegmentOut])
def list_transcript_segments(
    session_id: int,
    limit: int = Query(200, ge=1, le=500),
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
            "session_id": s.session_id,
            "segment_start": float(s.segment_start) if s.segment_start else 0,
            "segment_end": float(s.segment_end) if s.segment_end else 0,
            "text_content": s.text_content or "",
            "segment_type": s.segment_type or "",
            "asr_status": s.asr_status or TaskStatus.PENDING,
            "ai_score": float(s.ai_score) if s.ai_score else None,
        }
        for s in segments
    ]


@rest_router.get("/{session_id:int}/full-text", response_model=TranscriptFullTextResponse)
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
    # WebSocket 无法添加普通 Authorization 请求头，因此复用登录后签发的短时
    # HttpOnly 媒体 Cookie。未登录连接在 accept 前关闭，不能订阅任何真实话术。
    token = websocket.cookies.get(MEDIA_ACCESS_COOKIE)
    payload = decode_token(token) if token else None
    if payload is None or payload.get("type") != "media":
        await websocket.close(code=4401, reason="请先登录")
        return
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        await websocket.close(code=4401, reason="登录凭证无效")
        return
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None or user.status != "active":
            await websocket.close(code=4403, reason="账号已被禁用")
            return
    finally:
        db.close()

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
