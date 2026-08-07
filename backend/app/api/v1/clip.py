"""AI 自动剪辑 API。

功能：
- 查看剪辑任务与成片列表；
- 手动触发生成（整场重新生成 / 单条重剪）；
- 确认 / 丢弃成片（只生成内容，发布由用户人工完成）；
- 视频与封面文件服务（支持 Range，供前端 <video> 播放）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, settings
from app.core.database import get_db
from app.core.status import TaskStatus
from app.models.clip_clips import ClipClip
from app.models.live_sessions import LiveSession
from app.models.scraper_tasks import ScraperTask
from app.models.transcript_segments import TranscriptSegment
from app.schemas.clip import (
    ClipActionResponse,
    ClipClipResponse,
    ClipGenerateRequest,
    ClipSessionOverview,
    ClipTaskListResponse,
)
from app.services.tasks.control import collector_task_control
from app.services.tasks.views import serialize_scraper_task

router = APIRouter(prefix="/clip", tags=["AI自动剪辑"])

CLIP_TASK_TYPE = "clip_task"


def _storage_root() -> Path:
    return Path(PROJECT_ROOT) / settings.CLIP_STORAGE_DIR


def _serialize_clip(clip: ClipClip) -> ClipClipResponse:
    return ClipClipResponse(
        id=clip.id,
        session_id=clip.session_id,
        clip_order=clip.clip_order,
        status=clip.status,
        title=clip.title,
        description=clip.description,
        topics=clip.topics_json or [],
        segments=clip.segments_json or [],
        duration_seconds=clip.duration_seconds,
        video_path=clip.video_path,
        cover_path=clip.cover_path,
        is_manual=clip.is_manual or 0,
        error_message=clip.error_message,
        created_at=clip.created_at,
        updated_at=clip.updated_at,
    )


def _session_overview(db: Session, session_id: int) -> ClipSessionOverview:
    session = db.get(LiveSession, session_id)
    if not session:
        raise HTTPException(404, f"直播场次不存在: session_id={session_id}")
    task = (
        db.query(ScraperTask)
        .filter(
            ScraperTask.task_type == CLIP_TASK_TYPE,
            ScraperTask.session_id == session_id,
        )
        .order_by(ScraperTask.id.desc())
        .first()
    )
    clips = (
        db.query(ClipClip)
        .filter(ClipClip.session_id == session_id)
        .order_by(ClipClip.clip_order.asc(), ClipClip.id.asc())
        .all()
    )
    return ClipSessionOverview(
        session_id=session_id,
        session_title=session.session_title,
        anchor_name=session.anchor_name or session.anchor_nickname,
        anchor_nickname=session.anchor_nickname,
        anchor_avatar_url=session.anchor_avatar_url,
        douyin_id=session.douyin_id,
        live_start_time=session.live_start_time,
        live_duration_seconds=session.live_duration_seconds,
        detail_collection_status=session.detail_collection_status,
        task=serialize_scraper_task(task) if task else None,
        clips=[_serialize_clip(clip) for clip in clips],
    )


# ── 候选场次列表（页面下拉用：主播、话术转写、成片情况一目了然）──


@router.get("/candidate-sessions")
def list_candidate_sessions(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """可剪辑的候选场次：已结束、详情完整，按开播时间倒序。

    每条附带：主播信息、话术段数（转写情况）、已有成片数与最近任务状态，
    供前端下拉展示富信息，不用再单独查场次页。
    """
    from sqlalchemy import case as sql_case
    from sqlalchemy import func as sql_func

    transcript_stats = (
        db.query(
            TranscriptSegment.session_id.label("sid"),
            sql_func.count(TranscriptSegment.id).label("segment_count"),
            sql_func.sum(
                sql_case(
                    (TranscriptSegment.asr_status == "completed", 1),
                    else_=0,
                )
            ).label("completed_count"),
        )
        .group_by(TranscriptSegment.session_id)
        .subquery()
    )
    clip_stats = (
        db.query(
            ClipClip.session_id.label("sid"),
            sql_func.count(ClipClip.id).label("clip_count"),
            sql_func.sum(
                sql_case(
                    (ClipClip.status.in_(["draft", "approved"]), 1),
                    else_=0,
                )
            ).label("available_count"),
        )
        .group_by(ClipClip.session_id)
        .subquery()
    )
    rows = (
        db.query(
            LiveSession,
            transcript_stats.c.segment_count,
            transcript_stats.c.completed_count,
            clip_stats.c.clip_count,
            clip_stats.c.available_count,
        )
        .outerjoin(transcript_stats, transcript_stats.c.sid == LiveSession.id)
        .outerjoin(clip_stats, clip_stats.c.sid == LiveSession.id)
        .filter(
            LiveSession.live_status != "live",
            LiveSession.detail_collection_status == "complete",
        )
        .order_by(LiveSession.live_start_time.desc(), LiveSession.id.desc())
        .limit(limit)
        .all()
    )
    items: list[dict[str, Any]] = []
    for session, segment_count, completed_count, clip_count, available_count in rows:
        segment_count = int(segment_count or 0)
        completed_count = int(completed_count or 0)
        clip_count = int(clip_count or 0)
        available_count = int(available_count or 0)
        if segment_count == 0:
            transcript_status = "none"
        elif completed_count >= segment_count:
            transcript_status = "completed"
        elif completed_count > 0:
            transcript_status = "partial"
        else:
            transcript_status = "processing"
        items.append(
            {
                "session_id": session.id,
                "session_title": session.session_title,
                "anchor_name": session.anchor_name or session.anchor_nickname,
                "anchor_nickname": session.anchor_nickname,
                "anchor_avatar_url": session.anchor_avatar_url,
                "douyin_id": session.douyin_id,
                "live_start_time": session.live_start_time,
                "live_duration_seconds": session.live_duration_seconds,
                "transcript_segment_count": segment_count,
                "transcript_completed_count": completed_count,
                "transcript_status": transcript_status,
                "clip_count": clip_count,
                "clip_available_count": available_count,
                "clip_status": "has_clips" if available_count > 0 else "none",
            }
        )
    return items


# ── 任务列表与详情 ──


@router.get("/tasks", response_model=ClipTaskListResponse)
def list_clip_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(
        None, description="按任务状态过滤: pending/running/completed/failed"
    ),
    db: Session = Depends(get_db),
):
    """剪辑任务列表（按创建时间倒序）。"""
    query = db.query(ScraperTask).filter(ScraperTask.task_type == CLIP_TASK_TYPE)
    if status:
        query = query.filter(ScraperTask.status == status)
    total = query.count()
    tasks = (
        query.order_by(ScraperTask.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items: list[dict[str, Any]] = []
    for task in tasks:
        payload = serialize_scraper_task(task)
        if task.session_id:
            session = db.get(LiveSession, task.session_id)
            payload["session_title"] = session.session_title if session else None
            payload["anchor_name"] = (
                session.anchor_name or session.anchor_nickname if session else None
            )
        items.append(payload)
    return ClipTaskListResponse(total=total, items=items)


@router.get("/tasks/{task_id}", response_model=dict[str, Any])
def get_clip_task(task_id: int, db: Session = Depends(get_db)):
    """剪辑任务详情。"""
    task = db.get(ScraperTask, task_id)
    if not task or task.task_type != CLIP_TASK_TYPE:
        raise HTTPException(404, "剪辑任务不存在")
    return serialize_scraper_task(task)


# ── 场次剪辑总览与触发 ──


@router.get("/sessions/{session_id}", response_model=ClipSessionOverview)
def get_session_clips(session_id: int, db: Session = Depends(get_db)):
    """某场直播的剪辑总览：最近任务 + 全部成片。"""
    return _session_overview(db, session_id)


@router.post("/sessions/{session_id}/generate", response_model=ClipActionResponse)
def generate_session_clips(
    session_id: int,
    body: ClipGenerateRequest | None = None,
    db: Session = Depends(get_db),
):
    """手动触发整场 AI 剪辑（重新生成全部成片，覆盖旧 draft）。"""
    session = db.get(LiveSession, session_id)
    if not session:
        raise HTTPException(404, f"直播场次不存在: session_id={session_id}")
    options: dict[str, Any] = {"session_id": session_id}
    if body and body.user_hint:
        options["user_hint"] = body.user_hint
    try:
        task, created = collector_task_control.enqueue("clip", options)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    message = "已加入剪辑队列" if created else "该场次已有剪辑任务在排队或执行中"
    return ClipActionResponse(
        success=True, message=message, task=serialize_scraper_task(task)
    )


@router.post(
    "/sessions/{session_id}/clips/{clip_order}/regenerate",
    response_model=ClipActionResponse,
)
def regenerate_one_clip(
    session_id: int,
    clip_order: int,
    body: ClipGenerateRequest | None = None,
    db: Session = Depends(get_db),
):
    """手动重剪单条成片：AI 重新选段（可带 user_hint 指定主题），替换该序号成片。"""
    if clip_order < 1 or clip_order > 5:
        raise HTTPException(400, "clip_order 必须在 1-5 之间")
    session = db.get(LiveSession, session_id)
    if not session:
        raise HTTPException(404, f"直播场次不存在: session_id={session_id}")
    existing = (
        db.query(ClipClip)
        .filter(ClipClip.session_id == session_id, ClipClip.clip_order == clip_order)
        .first()
    )
    if not existing:
        raise HTTPException(404, f"该场次没有序号 {clip_order} 的成片，请先生成")
    options: dict[str, Any] = {"session_id": session_id, "clip_order": clip_order}
    if body and body.user_hint:
        options["user_hint"] = body.user_hint
    try:
        task, created = collector_task_control.enqueue("clip", options)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    message = (
        f"成片 #{clip_order} 已加入重剪队列"
        if created
        else "该场次已有剪辑任务在排队或执行中"
    )
    return ClipActionResponse(
        success=True, message=message, task=serialize_scraper_task(task)
    )


# ── 成片操作 ──


@router.post("/clips/{clip_id}/approve", response_model=ClipActionResponse)
def approve_clip(clip_id: int, db: Session = Depends(get_db)):
    """确认成片（标记为 approved，表示可人工发布）。"""
    clip = db.get(ClipClip, clip_id)
    if not clip:
        raise HTTPException(404, "成片不存在")
    if not clip.video_path:
        raise HTTPException(409, "成片尚未生成视频文件，无法确认")
    clip.status = "approved"
    db.commit()
    return ClipActionResponse(success=True, message="已确认成片，可复制文案发布")


@router.post("/clips/{clip_id}/discard", response_model=ClipActionResponse)
def discard_clip(clip_id: int, db: Session = Depends(get_db)):
    """丢弃成片（保留记录便于回溯，不再展示为可用成片）。"""
    clip = db.get(ClipClip, clip_id)
    if not clip:
        raise HTTPException(404, "成片不存在")
    clip.status = "discarded"
    db.commit()
    return ClipActionResponse(success=True, message="已丢弃成片")


@router.post("/tasks/{task_id}/cancel", response_model=ClipActionResponse)
def cancel_clip_task(task_id: int, db: Session = Depends(get_db)):
    """停止排队中或执行中的剪辑任务。"""
    task = db.get(ScraperTask, task_id)
    if not task or task.task_type != CLIP_TASK_TYPE:
        raise HTTPException(404, "剪辑任务不存在")
    try:
        collector_task_control.request_cancel(task_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return ClipActionResponse(
        success=True, message="已请求停止剪辑任务", task=serialize_scraper_task(task)
    )


# ── 文件服务（支持 Range，浏览器 <video> 直接播放）──


def _resolve_media_file(clip_id: int, kind: str, db: Session) -> Path:
    """按成片记录解析媒体文件绝对路径（防路径穿越：必须位于存储根目录内）。"""
    clip = db.get(ClipClip, clip_id)
    if not clip:
        raise HTTPException(404, "成片不存在")
    relative = clip.video_path if kind == "video" else clip.cover_path
    if not relative:
        raise HTTPException(404, "成片文件尚未生成")
    storage_root = _storage_root().resolve()
    path = (storage_root / relative).resolve()
    # 防止 ../ 或绝对路径越界读取存储目录外的任意文件
    if not path.is_relative_to(storage_root):
        raise HTTPException(400, "非法文件路径")
    if not path.exists() or not path.is_file():
        raise HTTPException(404, "成片文件已不存在（可能被清理）")
    return path


@router.get("/clips/{clip_id}/video")
def get_clip_video(clip_id: int, db: Session = Depends(get_db)):
    """成片视频文件（FileResponse 原生支持 Range 断点播放）。"""
    path = _resolve_media_file(clip_id, "video", db)
    return FileResponse(path, media_type="video/mp4")


@router.get("/clips/{clip_id}/cover")
def get_clip_cover(clip_id: int, db: Session = Depends(get_db)):
    """成片封面图。"""
    path = _resolve_media_file(clip_id, "cover", db)
    return FileResponse(path, media_type="image/jpeg")


@router.get("/clips/{clip_id}/subtitle")
def get_clip_subtitle(clip_id: int, db: Session = Depends(get_db)):
    """成片 ASS 字幕原文（前端预览/复查用，同样防路径穿越）。"""
    clip = db.get(ClipClip, clip_id)
    if not clip:
        raise HTTPException(404, "成片不存在")
    if not clip.subtitle_path:
        raise HTTPException(404, "成片没有字幕文件")
    storage_root = _storage_root().resolve()
    path = (storage_root / clip.subtitle_path).resolve()
    if not path.is_relative_to(storage_root):
        raise HTTPException(400, "非法文件路径")
    if not path.exists():
        raise HTTPException(404, "字幕文件已不存在")
    return FileResponse(path, media_type="text/plain; charset=utf-8")


# ── 汇总统计（采集控制中心侧边卡片可复用）──


@router.get("/stats")
def clip_stats(db: Session = Depends(get_db)):
    """剪辑模块统计：待确认成片数、今日生成数、最近失败任务。"""
    pending_count = (
        db.query(func.count(ClipClip.id))
        .filter(ClipClip.status == "draft", ClipClip.video_path.isnot(None))
        .scalar()
        or 0
    )
    failed_task_count = (
        db.query(func.count(ScraperTask.id))
        .filter(
            ScraperTask.task_type == CLIP_TASK_TYPE,
            ScraperTask.status == TaskStatus.FAILED,
        )
        .scalar()
        or 0
    )
    return {
        "pending_confirm_count": pending_count,
        "failed_task_count": failed_task_count,
        "storage_root": str(_storage_root()),
        "storage_available": True,
    }
