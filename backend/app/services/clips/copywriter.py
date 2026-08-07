"""AI 选段结果校验与成片记录落库。

AI 输出不可信：时间戳可能编造、时长可能越界、字段可能缺失。
这里统一做「真实话术时间戳映射校验 + 时长约束 + 落库」，保证后续
ffmpeg 剪辑拿到的每个片段都能在 transcript_segments 中找到依据。
校验失败的单个方案直接丢弃，不浪费剪辑资源；全部失败才抛错让任务重试。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.logger import logger
from app.models.clip_clips import ClipClip
from app.services.clips.segment_selector import (
    MAX_CLIP_SECONDS,
    MAX_SEGMENTS_PER_CLIP,
    MIN_CLIP_SECONDS,
    TIMESTAMP_TOLERANCE,
    TranscriptUnit,
)


def _match_unit(
    units: list[TranscriptUnit], start: float, end: float
) -> TranscriptUnit | None:
    """在真实话术中查找与 AI 时间戳匹配的话术单元（±容差，兜底用）。"""
    best: TranscriptUnit | None = None
    best_distance = float("inf")
    for unit in units:
        distance = abs(unit.start - start) + abs(unit.end - end)
        if distance < best_distance:
            best_distance = distance
            best = unit
    if best is None or best_distance > TIMESTAMP_TOLERANCE * 2:
        return None
    return best


def _resolve_unit(
    raw_seg: dict[str, Any], units: list[TranscriptUnit]
) -> TranscriptUnit | None:
    """按 AI 输出解析话术单元：优先行号 index（防时间戳幻觉），时间戳容差兜底。"""
    index = raw_seg.get("index")
    if isinstance(index, (int, float)) and not isinstance(index, bool):
        unit_index = int(index) - 1
        if 0 <= unit_index < len(units):
            return units[unit_index]
        return None
    try:
        start = float(raw_seg["start"])
        end = float(raw_seg["end"])
    except (KeyError, TypeError, ValueError):
        return None
    return _match_unit(units, start, end)


def normalize_clip(
    raw: dict[str, Any], units: list[TranscriptUnit], order: int
) -> dict[str, Any] | None:
    """校验并规范化一条 AI 方案；不合法返回 None。"""
    title = str(raw.get("title") or "").strip()
    description = str(raw.get("description") or "").strip()
    raw_segments = raw.get("segments")
    topics = raw.get("topics") or []

    if not title or not description:
        logger.warning("剪辑方案 #%s 缺少标题或文案，已丢弃", order)
        return None
    if not isinstance(raw_segments, list) or not raw_segments:
        logger.warning("剪辑方案 #%s 没有片段，已丢弃", order)
        return None
    if len(raw_segments) > MAX_SEGMENTS_PER_CLIP:
        logger.warning(
            "剪辑方案 #%s 片段数 %s 超上限，已丢弃", order, len(raw_segments)
        )
        return None

    segments: list[dict[str, Any]] = []
    duration = 0.0
    previous_end: float | None = None
    for seg in raw_segments:
        unit = _resolve_unit(seg, units)
        if unit is None:
            logger.warning(
                "剪辑方案 #%s 片段 %s 在话术中找不到依据，已丢弃",
                order,
                {k: seg.get(k) for k in ("index", "start", "end")},
            )
            return None
        if unit.end <= unit.start or unit.end - unit.start < 3:
            logger.warning("剪辑方案 #%s 片段时长异常，已丢弃", order)
            return None
        # 片段间轻微重叠（≤2 秒）视为拼接误差，直接吸附对齐避免重复画面
        if previous_end is not None and unit.start < previous_end - 2:
            logger.warning("剪辑方案 #%s 片段与上一段严重重叠，已丢弃", order)
            return None
        previous_end = unit.end
        segments.append({"start": unit.start, "end": unit.end, "text": unit.text})
        duration += unit.end - unit.start

    if not (MIN_CLIP_SECONDS <= duration <= MAX_CLIP_SECONDS):
        logger.warning(
            "剪辑方案 #%s 总时长 %.1f 秒超出 %s-%s，已丢弃",
            order,
            duration,
            MIN_CLIP_SECONDS,
            MAX_CLIP_SECONDS,
        )
        return None

    cleaned_topics = [str(t).strip() for t in topics if str(t).strip()][:6]
    return {
        "clip_order": order,
        "title": title[:200],
        "theme": str(raw.get("theme") or "")[:200],
        "description": description,
        "topics": cleaned_topics,
        "segments": segments,
        "duration_seconds": round(duration),
    }


def save_clip_records(
    db: Session,
    *,
    task_id: int,
    session_id: int,
    normalized: list[dict[str, Any]],
    is_manual: bool = False,
    ai_raw: dict[str, Any] | None = None,
    source_text: str | None = None,
) -> list[ClipClip]:
    """把校验通过的方案写入 clip_clips。

    自动模式（is_manual=False）先清掉该场旧的 draft/failed 记录再插入，
    且按校验通过顺序从 1 重新编号（丢弃的方案不占位）；
    手动重剪不删除旧记录（旧成片可能在发布/确认中），新记录渲染成功后
    由 clip_service 把同序号的旧记录标记为 discarded，渲染失败旧记录保留。
    """
    if not is_manual:
        for position, item in enumerate(normalized, start=1):
            item["clip_order"] = position
        db.query(ClipClip).filter(
            ClipClip.session_id == session_id,
            ClipClip.status.in_(["draft", "failed"]),
        ).delete(synchronize_session=False)
        db.flush()

    records: list[ClipClip] = []
    for item in normalized:
        record = ClipClip(
            task_id=task_id,
            session_id=session_id,
            clip_order=item["clip_order"],
            status="draft",
            title=item["title"],
            description=item["description"],
            topics_json=item["topics"],
            segments_json=item["segments"],
            duration_seconds=item["duration_seconds"],
            source_text=source_text,
            ai_raw_json=ai_raw,
            is_manual=1 if is_manual else 0,
        )
        db.add(record)
        records.append(record)
    db.commit()
    for record in records:
        db.refresh(record)
    return records
