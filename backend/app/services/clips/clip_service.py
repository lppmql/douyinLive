"""AI 自动剪辑编排服务：选段 -> 落库 -> 下载回放 -> 渲染成片。

供 collector_task_control 的 run_clip_batch 调用（to_thread 线程中执行）。
进度通过 report 回调上报，取消通过 should_cancel 检查点响应。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import exists
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, settings
from app.core.logger import logger
from app.models.clip_clips import ClipClip
from app.models.live_sessions import LiveSession
from app.models.transcript_segments import TranscriptSegment
from app.services.clips.copywriter import normalize_clip, save_clip_records
from app.services.clips.ffmpeg_clipper import render_clip
from app.services.clips.replay_downloader import ensure_replay_file
from app.services.clips.segment_selector import select_clips
from app.services.tasks.exceptions import TaskCancellationRequested

ProgressReporter = Callable[[str, int, int, int, str, dict[str, Any] | None], None]
CancellationChecker = Callable[[], bool]


def _storage_root() -> Path:
    """data/videos 绝对根目录（成片路径存相对该目录的路径）。"""
    return Path(PROJECT_ROOT) / settings.CLIP_STORAGE_DIR


def _relative_storage_path(path: Path) -> str:
    return str(path.relative_to(_storage_root()))


def pending_clip_session_ids(db: Session, limit: int | None = None) -> list[int]:
    """历史场次补生成：有已完成话术、且当前没有待确认成片的场次。"""
    has_draft = exists().where(
        ClipClip.session_id == LiveSession.id,
        ClipClip.status.in_(["draft", "approved"]),
    )
    has_transcript = exists().where(
        TranscriptSegment.session_id == LiveSession.id,
        TranscriptSegment.asr_status == "completed",
    )
    query = (
        db.query(LiveSession.id)
        .filter(
            LiveSession.live_status != "live",
            LiveSession.detail_collection_status == "complete",
            has_transcript,
            ~has_draft,
        )
        .order_by(LiveSession.live_start_time.desc(), LiveSession.id.desc())
    )
    if limit is not None:
        query = query.limit(max(1, limit))
    return [row[0] for row in query.all()]


def generate_and_render_session(
    db: Session,
    session_id: int,
    *,
    task_id: int,
    report: ProgressReporter,
    should_cancel: CancellationChecker,
    user_hint: str | None = None,
    clip_order: int | None = None,
) -> dict[str, Any]:
    """单场完整管线：AI 选段 -> 校验落库 -> 回放下载 -> 逐条渲染。

    Args:
        clip_order: 手动重剪时指定要替换的成片序号（只渲染这一条）。
    Returns:
        统计结果 dict。
    """
    session = db.get(LiveSession, session_id)
    if not session:
        raise ValueError(f"直播场次不存在: session_id={session_id}")

    # ── 1. AI 选段 ──
    report(
        "clip_select",
        5,
        0,
        5,
        "正在让 AI 从整场话术中挑选短视频片段",
        {"session_id": session_id},
    )
    result = select_clips(
        db,
        session_id,
        session_title=session.session_title,
        anchor_name=session.anchor_name,
        count=5 if clip_order is None else 1,
        user_hint=user_hint,
    )
    units = result["units"]
    raw_clips = result["clips"]

    if clip_order is not None:
        # 手动重剪：只处理目标序号对应的一条方案
        index = clip_order - 1
        candidates = [raw_clips[index]] if 0 <= index < len(raw_clips) else []
        start_order = clip_order
    else:
        candidates = raw_clips
        start_order = 1

    normalized: list[dict[str, Any]] = []
    for i, raw in enumerate(candidates, start=start_order):
        item = normalize_clip(raw, units, i)
        if item is not None:
            normalized.append(item)

    if not normalized:
        raise ValueError(
            "AI 选出的片段没有一条通过校验（时间戳或时长不合法），任务失败"
        )

    records = save_clip_records(
        db,
        task_id=task_id,
        session_id=session_id,
        normalized=normalized,
        is_manual=clip_order is not None,
        ai_raw={"clips": raw_clips},
    )
    logger.info("场次 %s 成片方案落库 %s 条", session_id, len(records))

    # ── 2. 下载回放 ──
    report(
        "replay_download",
        20,
        0,
        len(records),
        "正在下载直播回放视频",
        {"session_id": session_id},
    )
    replay = ensure_replay_file(db, session_id)

    # ── 3. 逐条渲染 ──
    rendered = 0
    failed: list[dict[str, Any]] = []
    try:
        for position, record in enumerate(records, start=1):
            if should_cancel():
                raise TaskCancellationRequested("用户已停止任务")
            report(
                "clip_render",
                30 + int(position / max(len(records), 1) * 65),
                position,
                len(records),
                f"正在剪辑成片 {position}/{len(records)}：{record.title}",
                {"session_id": session_id, "clip_order": record.clip_order},
            )
            try:
                paths = render_clip(
                    replay,
                    record.segments_json,
                    clip_order=record.clip_order,
                    session_id=session_id,
                )
                record.video_path = _relative_storage_path(paths["video"])
                record.cover_path = _relative_storage_path(paths["cover"])
                record.subtitle_path = _relative_storage_path(paths["subtitle"])
                record.status = "draft"
                record.error_message = None
                db.commit()
                rendered += 1
                # 手动重剪：新成片渲染成功后，把同序号的旧记录标记为已丢弃
                if clip_order is not None:
                    db.query(ClipClip).filter(
                        ClipClip.session_id == session_id,
                        ClipClip.clip_order == record.clip_order,
                        ClipClip.id != record.id,
                        ClipClip.status.in_(["draft", "approved"]),
                    ).update({"status": "discarded"}, synchronize_session=False)
                    db.commit()
            except Exception as exc:
                db.rollback()
                record.status = "failed"
                record.error_message = str(exc)[:500]
                db.commit()
                failed.append(
                    {"clip_order": record.clip_order, "message": str(exc)[:300]}
                )
                logger.exception(
                    "成片渲染失败 session=%s clip=%s: %s",
                    session_id,
                    record.clip_order,
                    exc,
                )
    finally:
        # 任务中断（取消/异常）后，把未渲染的 draft 记录标记失败，
        # 避免残留“待确认但无法播放”的成片卡住该场次的自动补生成。
        db.query(ClipClip).filter(
            ClipClip.session_id == session_id,
            ClipClip.status == "draft",
            ClipClip.video_path.is_(None),
        ).update(
            {
                "status": "failed",
                "error_message": "剪辑未完成（任务取消或中断），请重新生成",
            },
            synchronize_session=False,
        )
        db.commit()

    result = {
        "session_id": session_id,
        "selected_count": len(normalized),
        "rendered_count": rendered,
        "failed_count": len(failed),
        "errors": failed[:10],
    }
    report(
        "clip_render",
        99,
        rendered,
        len(records),
        f"剪辑完成：成功 {rendered} 条，失败 {len(failed)} 条",
        result,
    )
    return result
