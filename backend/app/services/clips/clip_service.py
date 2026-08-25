"""AI 自动剪辑编排服务：选段 -> 落库 -> 下载回放 -> 渲染成片。

供 collector_task_control 的 run_clip_batch 调用（to_thread 线程中执行）。
进度通过 report 回调上报，取消通过 should_cancel 检查点响应。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import and_, exists, or_
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, settings
from app.core.logger import logger
from app.models.clip_clips import ClipClip
from app.models.live_sessions import LiveSession
from app.models.transcript_segments import TranscriptSegment
from app.services.asr.control import is_asr_engine_running
from app.services.asr.timestamp_alignment import (
    aggregate_timestamp_precision,
    remap_corrected_text,
)
from app.services.clips.ass_subtitle import build_subtitle_cues
from app.services.clips.copywriter import normalize_clip, save_clip_records
from app.services.clips.ffmpeg_clipper import (
    render_clip,
    require_clip_ffmpeg,
    rerender_subtitles,
)
from app.services.clips.replay_downloader import (
    ensure_replay_file,
    has_replay_source,
    replay_file_is_usable,
    replay_path,
)
from app.services.clips.segment_selector import select_clips
from app.services.clips.subtitle_aligner import enrich_records_with_precise_subtitles
from app.services.tasks.exceptions import TaskCancellationRequested

ProgressReporter = Callable[[str, int, int, int, str, dict[str, Any] | None], None]
CancellationChecker = Callable[[], bool]
DISCARDED_CLIP_RETENTION_PER_SESSION = 10


def _storage_root() -> Path:
    """data/videos 绝对根目录（成片路径存相对该目录的路径）。"""
    return Path(PROJECT_ROOT) / settings.CLIP_STORAGE_DIR


def _relative_storage_path(path: Path) -> str:
    return str(path.relative_to(_storage_root()))


def _absolute_storage_path(relative: str | None) -> Path | None:
    """安全解析数据库中的媒体相对路径，禁止越出视频存储目录。"""
    if not relative:
        return None
    root = _storage_root().resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("成片媒体路径非法")
    return path


def _cleanup_artifact_snapshots(
    snapshots: list[dict[str, Any]],
    *,
    protected_paths: set[Path],
) -> None:
    """删除已超过保留上限的版本文件；路径必须位于视频根目录且不被当前版本引用。"""
    path_keys = (
        "video_path",
        "clean_video_path",
        "cover_path",
        "subtitle_path",
        "subtitle_srt_path",
    )
    candidate_parents: set[Path] = set()
    for snapshot in snapshots:
        for key in path_keys:
            try:
                path = _absolute_storage_path(snapshot.get(key))
            except ValueError as exc:
                logger.warning("跳过非法历史成片路径清理: %s", exc)
                continue
            if not path or path in protected_paths:
                continue
            try:
                path.unlink(missing_ok=True)
                candidate_parents.add(path.parent)
            except OSError as exc:
                logger.warning("清理过期成片文件失败 %s: %s", path, exc)
    for parent in sorted(
        candidate_parents, key=lambda item: len(item.parts), reverse=True
    ):
        try:
            parent.rmdir()
        except OSError:
            # v1 目录通常还保留 clean.mp4；目录非空时无需报错。
            pass


def prune_discarded_clips(
    db: Session,
    session_id: int,
    *,
    keep: int = DISCARDED_CLIP_RETENTION_PER_SESSION,
) -> int:
    """按场次保留最近的已丢弃成片，安全清理更旧且可判定为新管线的记录。"""
    candidates = (
        db.query(ClipClip)
        .filter(
            ClipClip.session_id == session_id,
            ClipClip.status == "discarded",
            # 有 clean 路径的是 clip_id 唯一目录；全空路径是已清理的失败记录。
            # 旧版共享路径没有 clean 且 video 非空，无法证明独占，保留避免误删。
            or_(
                ClipClip.clean_video_path.isnot(None),
                and_(
                    ClipClip.video_path.is_(None),
                    ClipClip.cover_path.is_(None),
                    ClipClip.subtitle_path.is_(None),
                    ClipClip.subtitle_srt_path.is_(None),
                ),
            ),
        )
        .order_by(ClipClip.id.desc())
        .all()
    )
    stale = candidates[max(0, keep) :]
    if not stale:
        return 0

    snapshots: list[dict[str, Any]] = []
    for record in stale:
        snapshots.append(
            {
                "video_path": record.video_path,
                "clean_video_path": record.clean_video_path,
                "cover_path": record.cover_path,
                "subtitle_path": record.subtitle_path,
                "subtitle_srt_path": record.subtitle_srt_path,
            }
        )
        snapshots.extend(list(record.artifact_versions_json or []))
        db.delete(record)
    db.commit()
    _cleanup_artifact_snapshots(snapshots, protected_paths=set())
    return len(stale)


def _mark_unrendered_records_failed(db: Session, session_id: int) -> None:
    """取消或异常时清理待确认假象，避免无视频草稿阻止后续自动补生成。"""
    db.rollback()
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


def _subtitle_precision(segments: list[dict[str, Any]]) -> str:
    sources = {
        str(item.get("subtitle_precision") or "segment_estimated") for item in segments
    }
    return aggregate_timestamp_precision(sources)


def _render_qc(
    paths: dict[str, Path],
    segments: list[dict[str, Any]],
    *,
    alignment_warnings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """记录可复核的基础质检事实，不用猜测视频内容质量。"""
    cues = build_subtitle_cues(segments)
    return {
        "subtitle_cue_count": len(cues),
        "subtitle_precision": _subtitle_precision(segments),
        "video_bytes": paths["video"].stat().st_size if paths["video"].exists() else 0,
        "clean_video_available": paths["clean_video"].exists(),
        "ass_available": paths["subtitle"].exists(),
        "srt_available": paths["subtitle_srt"].exists(),
        "subtitle_alignment_warnings": alignment_warnings or [],
    }


def _preflight_clip_generation(db: Session, session_id: int) -> dict[str, Any]:
    """在产生 AI 费用前验证真实话术、回放来源和本机媒体依赖。"""
    require_clip_ffmpeg()
    transcripts = (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.session_id == session_id,
            TranscriptSegment.asr_status == "completed",
        )
        .all()
    )
    if not transcripts:
        raise ValueError("场次没有已完成的真实话术，不能生成 AI 剪辑")

    local_replay = replay_path(session_id)
    local_replay_usable = replay_file_is_usable(local_replay)
    has_source = has_replay_source(db, session_id)
    if not local_replay_usable and not has_source:
        raise ValueError("场次没有真实回放文件或流地址，不能生成 AI 剪辑")

    missing_word_timestamps = sum(
        1 for item in transcripts if not item.word_timestamps_json
    )
    if missing_word_timestamps and not is_asr_engine_running():
        raise RuntimeError(
            f"场次有 {missing_word_timestamps} 段话术缺少逐字时间戳，"
            "请先启动 FunASR，再生成剪辑"
        )
    return {
        "transcript_count": len(transcripts),
        "missing_word_timestamp_count": missing_word_timestamps,
        "replay_source": "local" if local_replay_usable else "stream",
    }


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

    preflight = _preflight_clip_generation(db, session_id)

    # ── 1. AI 选段 ──
    report(
        "clip_select",
        5,
        0,
        5,
        "正在让 AI 从整场话术中挑选短视频片段",
        {"session_id": session_id, "preflight": preflight},
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
    prune_discarded_clips(db, session_id)
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
    try:
        replay = ensure_replay_file(db, session_id)
        alignment = enrich_records_with_precise_subtitles(
            db,
            replay,
            records,
            should_cancel=should_cancel,
        )
    except Exception:
        _mark_unrendered_records_failed(db, session_id)
        raise
    report(
        "subtitle_align",
        28,
        alignment["aligned_segment_count"],
        alignment["aligned_segment_count"] + alignment["fallback_segment_count"],
        (
            f"候选字幕精确对齐完成：精确 {alignment['aligned_segment_count']} 段，"
            f"估算降级 {alignment['fallback_segment_count']} 段"
        ),
        {"session_id": session_id, **alignment},
    )
    warnings_by_clip: dict[int, list[dict[str, Any]]] = {}
    for warning in alignment.get("fallback_warnings", []):
        clip_id = int(warning.get("clip_id") or 0)
        warnings_by_clip.setdefault(clip_id, []).append(warning)

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
                    clip_id=record.id,
                    render_version=record.render_version or 1,
                )
                record.video_path = _relative_storage_path(paths["video"])
                record.clean_video_path = _relative_storage_path(paths["clean_video"])
                record.cover_path = _relative_storage_path(paths["cover"])
                record.subtitle_path = _relative_storage_path(paths["subtitle"])
                record.subtitle_srt_path = _relative_storage_path(paths["subtitle_srt"])
                record.subtitle_precision = _subtitle_precision(record.segments_json)
                record.qc_json = _render_qc(
                    paths,
                    record.segments_json,
                    alignment_warnings=warnings_by_clip.get(record.id, []),
                )
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
                    prune_discarded_clips(db, session_id)
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
        _mark_unrendered_records_failed(db, session_id)

    result = {
        "session_id": session_id,
        "selected_count": len(normalized),
        "rendered_count": rendered,
        "failed_count": len(failed),
        "subtitle_alignment_warning_count": len(
            alignment.get("fallback_warnings", [])
        ),
        "subtitle_alignment_warnings": alignment.get("fallback_warnings", [])[:20],
        "preflight": preflight,
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


def rerender_clip_subtitles(
    db: Session,
    clip_id: int,
    *,
    requested_segments: list[dict[str, Any]] | None = None,
    target_render_version: int | None = None,
) -> ClipClip:
    """只重制一条成片的字幕，并保留上一版文件和路径快照。"""
    record = db.get(ClipClip, clip_id)
    if not record:
        raise ValueError("成片不存在")
    current_version = int(record.render_version or 1)
    if target_render_version is not None:
        if target_render_version <= current_version:
            # 任务在数据库提交成片后、提交任务状态前崩溃：恢复时直接复用已完成版本。
            return record
        if target_render_version != current_version + 1:
            raise ValueError("字幕目标版本与当前成片版本不连续，请刷新页面后重试")
    clean_video = _absolute_storage_path(record.clean_video_path)
    if not clean_video or not clean_video.exists():
        raise ValueError("该成片没有可复用的无字幕底片，请使用“重剪”重新生成整条视频")

    original_segments = list(record.segments_json or [])
    segments = original_segments
    if requested_segments is not None:
        if len(requested_segments) != len(original_segments):
            raise ValueError("字幕段数不能改变；需要调整画面时间请使用“重剪”")
        segments = []
        for index, (original, requested) in enumerate(
            zip(original_segments, requested_segments, strict=True), start=1
        ):
            try:
                original_start = float(original["start"])
                original_end = float(original["end"])
                requested_start = float(requested["start"])
                requested_end = float(requested["end"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"第 {index} 段字幕时间格式错误") from exc
            if (
                abs(original_start - requested_start) > 0.05
                or abs(original_end - requested_end) > 0.05
            ):
                raise ValueError(
                    "仅重制字幕不能修改画面起止时间；需要改时间请使用“重剪”"
                )
            text = str(requested.get("text") or "").strip()
            if not text:
                raise ValueError(f"第 {index} 段字幕不能为空")
            if len(text) > 5000:
                raise ValueError(f"第 {index} 段字幕过长")
            old_text = str(original.get("text") or "")
            old_words = list(original.get("words") or [])
            if text == old_text:
                remapped_words = old_words
                precision = str(
                    original.get("subtitle_precision") or "segment_estimated"
                )
            else:
                remapped_words, precision = remap_corrected_text(
                    old_text,
                    text,
                    old_words,
                    str(original.get("subtitle_precision") or "segment_estimated"),
                )
            segments.append(
                {
                    **original,
                    "text": text,
                    "words": remapped_words,
                    "subtitle_precision": precision,
                }
            )

    next_version = target_render_version or current_version + 1
    paths = rerender_subtitles(
        clean_video,
        segments,
        session_id=record.session_id,
        clip_id=record.id,
        render_version=next_version,
    )
    history = list(record.artifact_versions_json or [])
    history.append(
        {
            "version": current_version,
            "video_path": record.video_path,
            "cover_path": record.cover_path,
            "subtitle_path": record.subtitle_path,
            "subtitle_srt_path": record.subtitle_srt_path,
            "subtitle_precision": record.subtitle_precision,
        }
    )
    evicted_history = history[:-20]
    record.artifact_versions_json = history[-20:]
    record.render_version = next_version
    record.segments_json = segments
    record.video_path = _relative_storage_path(paths["video"])
    record.cover_path = _relative_storage_path(paths["cover"])
    record.subtitle_path = _relative_storage_path(paths["subtitle"])
    record.subtitle_srt_path = _relative_storage_path(paths["subtitle_srt"])
    record.subtitle_precision = _subtitle_precision(segments)
    record.qc_json = _render_qc(paths, segments)
    record.status = "draft"
    record.error_message = None
    db.commit()
    db.refresh(record)
    protected_paths = {
        path.resolve()
        for path in (
            _absolute_storage_path(record.clean_video_path),
            _absolute_storage_path(record.video_path),
            _absolute_storage_path(record.cover_path),
            _absolute_storage_path(record.subtitle_path),
            _absolute_storage_path(record.subtitle_srt_path),
        )
        if path is not None
    }
    _cleanup_artifact_snapshots(
        evicted_history,
        protected_paths=protected_paths,
    )
    return record
