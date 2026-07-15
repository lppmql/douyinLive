"""直播知识时间片同步与混合检索。"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.comments import Comment
from app.models.knowledge_time_slices import KnowledgeTimeSlice
from app.models.live_metrics import LiveMetric
from app.models.live_sessions import LiveSession
from app.models.transcript_segments import TranscriptSegment
from app.core.config import settings
from app.core.observability import KNOWLEDGE_SEARCH_TOTAL, KNOWLEDGE_SYNC_TOTAL

PARSER_VERSION = "time-slice-v1"
DEFAULT_SLICE_SECONDS = settings.KNOWLEDGE_SLICE_SECONDS
COUNT_METRICS = (
    "exposure_count",
    "enter_count",
    "like_count",
    "comment_count",
    "follow_count",
    "clue_count",
    "windmill_click_count",
    "card_click_count",
    "wechat_add_count",
    "form_submit_count",
)


def format_offset(seconds: int | float | Decimal | None) -> str:
    value = max(0, int(float(seconds or 0)))
    hours, remainder = divmod(value, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _relative_seconds(event_time, live_start_time) -> int | None:
    if event_time is None or live_start_time is None:
        return None
    return int((event_time - live_start_time).total_seconds())


def _source_duration(
    session: LiveSession,
    transcripts: list[TranscriptSegment],
    comments: list[Comment],
    metrics: list[LiveMetric],
) -> int:
    candidates = [int(session.live_duration_seconds or 0)]
    candidates.extend(int(float(row.segment_end or row.segment_start or 0)) for row in transcripts)
    if session.live_start_time:
        candidates.extend(
            offset + 1
            for row in comments
            if (offset := _relative_seconds(row.comment_time, session.live_start_time)) is not None
        )
        candidates.extend(
            offset + 1
            for row in metrics
            if (offset := _relative_seconds(row.metric_time, session.live_start_time)) is not None
        )
    return max(candidates, default=0)


def _metric_summary(rows: list[LiveMetric]) -> dict[str, Any]:
    if not rows:
        return {}
    ordered = sorted(rows, key=lambda row: row.metric_time)
    first = ordered[0]
    last = ordered[-1]
    summary: dict[str, Any] = {
        "point_count": len(rows),
        "avg_online_count": round(sum(row.online_count or 0 for row in rows) / len(rows), 2),
        "peak_online_count": max(row.online_count or 0 for row in rows),
    }
    for field in COUNT_METRICS:
        first_value = int(getattr(first, field) or 0)
        last_value = int(getattr(last, field) or 0)
        summary[field] = {
            "first": first_value,
            "last": last_value,
            "delta": max(0, last_value - first_value),
        }
    return summary


def _slice_payload(
    session: LiveSession,
    index: int,
    slice_seconds: int,
    duration: int,
    transcripts: list[TranscriptSegment],
    comments: list[Comment],
    metrics: list[LiveMetric],
    unmapped_comment_count: int,
) -> dict[str, Any]:
    start_seconds = index * slice_seconds
    end_seconds = min(duration, (index + 1) * slice_seconds)
    transcript_rows = [
        row for row in transcripts
        if start_seconds <= int(float(row.segment_start or 0)) < max(end_seconds, start_seconds + 1)
    ]
    comment_rows = []
    for row in comments:
        offset = _relative_seconds(row.comment_time, session.live_start_time)
        if offset is not None and start_seconds <= offset < max(end_seconds, start_seconds + 1):
            comment_rows.append(row)
    metric_rows = []
    for row in metrics:
        offset = _relative_seconds(row.metric_time, session.live_start_time)
        if offset is not None and start_seconds <= offset < max(end_seconds, start_seconds + 1):
            metric_rows.append(row)

    transcript_text = "\n".join(
        f"[{format_offset(row.segment_start)}-{format_offset(row.segment_end)}] {row.text_content or ''}".strip()
        for row in transcript_rows
        if row.text_content
    )
    comments_text = "\n".join(
        f"[{row.comment_time:%Y-%m-%d %H:%M:%S}] {row.user_nickname or '匿名用户'}"
        f"{' [高意向]' if row.is_high_intent else ''}：{row.comment_content or ''}"
        for row in comment_rows
    )
    metric_summary = _metric_summary(metric_rows)
    anchor_name = session.anchor_name or session.anchor_nickname or "未知主播"
    time_range = f"{format_offset(start_seconds)}-{format_offset(end_seconds)}"
    metric_search_text = ""
    if metric_summary:
        metric_search_text = (
            f"分钟指标 采样{metric_summary['point_count']}次 "
            f"平均在线人数{metric_summary['avg_online_count']} "
            f"峰值在线人数{metric_summary['peak_online_count']} "
            f"评论变化{metric_summary['comment_count']['delta']}"
        )
    search_text = "\n".join(filter(None, (
        f"主播 {anchor_name}",
        f"场次 {session.id} {session.session_title or '未命名直播'}",
        f"时间片 {time_range}",
        transcript_text,
        comments_text,
        metric_search_text,
        json.dumps(metric_summary, ensure_ascii=False, sort_keys=True) if metric_summary else "",
    )))
    hash_source = f"{search_text}\nunmapped_comment_count={unmapped_comment_count if index == 0 else 0}"
    source_hash = hashlib.sha256(hash_source.encode("utf-8")).hexdigest()
    return {
        "session_id": session.id,
        "slice_index": index,
        "slice_start_seconds": start_seconds,
        "slice_end_seconds": end_seconds,
        "slice_start_time": session.live_start_time + timedelta(seconds=start_seconds) if session.live_start_time else None,
        "slice_end_time": session.live_start_time + timedelta(seconds=end_seconds) if session.live_start_time else None,
        "anchor_name": anchor_name,
        "session_title": session.session_title,
        "transcript_text": transcript_text or None,
        "comments_text": comments_text or None,
        "comment_count": len(comment_rows),
        "high_intent_comment_count": sum(1 for row in comment_rows if row.is_high_intent),
        "unmapped_comment_count": unmapped_comment_count if index == 0 else 0,
        "metric_point_count": len(metric_rows),
        "avg_online_count": metric_summary.get("avg_online_count", 0),
        "peak_online_count": metric_summary.get("peak_online_count", 0),
        "metric_summary_json": json.dumps(metric_summary, ensure_ascii=False, sort_keys=True) if metric_summary else None,
        "search_text": search_text,
        "source_hash": source_hash,
        "parser_version": PARSER_VERSION,
    }


def sync_session_time_slices(
    db: Session,
    session_id: int,
    slice_seconds: int = DEFAULT_SLICE_SECONDS,
) -> dict[str, int]:
    """幂等构建一场直播的时间片，不猜测缺少平台时间的评论归属。"""
    session = db.get(LiveSession, session_id)
    if not session:
        return {"slice_count": 0, "created_count": 0, "updated_count": 0, "unchanged_count": 0, "deleted_count": 0, "unmapped_comment_count": 0}
    transcripts = db.query(TranscriptSegment).filter(
        TranscriptSegment.session_id == session_id,
        TranscriptSegment.asr_status == "completed",
    ).order_by(TranscriptSegment.segment_start, TranscriptSegment.id).all()
    comments = db.query(Comment).filter(Comment.session_id == session_id).order_by(Comment.comment_time, Comment.id).all()
    metrics = db.query(LiveMetric).filter(LiveMetric.session_id == session_id).order_by(LiveMetric.metric_time, LiveMetric.id).all()
    unmapped_comment_count = sum(
        1
        for row in comments
        if (offset := _relative_seconds(row.comment_time, session.live_start_time)) is None or offset < 0
    )
    duration = _source_duration(session, transcripts, comments, metrics)
    has_sources = bool(transcripts or comments or metrics)
    slice_count = max(1, math.ceil(max(duration, 1) / slice_seconds)) if has_sources else 0
    existing = {
        row.slice_index: row
        for row in db.query(KnowledgeTimeSlice).filter(KnowledgeTimeSlice.session_id == session_id).all()
    }
    counts = defaultdict(int)
    for index in range(slice_count):
        payload = _slice_payload(
            session,
            index,
            slice_seconds,
            max(duration, slice_seconds),
            transcripts,
            comments,
            metrics,
            unmapped_comment_count,
        )
        row = existing.pop(index, None)
        if row is None:
            db.add(KnowledgeTimeSlice(**payload))
            counts["created_count"] += 1
        elif row.source_hash == payload["source_hash"] and row.parser_version == PARSER_VERSION:
            counts["unchanged_count"] += 1
        else:
            for key, value in payload.items():
                setattr(row, key, value)
            counts["updated_count"] += 1
    for row in existing.values():
        db.delete(row)
        counts["deleted_count"] += 1
    db.commit()
    for result_name in ("created_count", "updated_count", "unchanged_count", "deleted_count"):
        if counts[result_name]:
            KNOWLEDGE_SYNC_TOTAL.labels(result=result_name.removesuffix("_count")).inc(counts[result_name])
    return {
        "slice_count": slice_count,
        "created_count": counts["created_count"],
        "updated_count": counts["updated_count"],
        "unchanged_count": counts["unchanged_count"],
        "deleted_count": counts["deleted_count"],
        "unmapped_comment_count": unmapped_comment_count,
    }


def _query_terms(question: str) -> list[str]:
    normalized = question.strip().lower()
    terms = {token for token in re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", normalized) if len(token) >= 2}
    for sequence in re.findall(r"[\u4e00-\u9fff]{3,}", normalized):
        for size in (2, 3, 4):
            terms.update(sequence[index:index + size] for index in range(len(sequence) - size + 1))
    return sorted(terms, key=len, reverse=True)[:40]


def search_time_slices(db: Session, question: str, limit: int = 8) -> list[dict[str, Any]]:
    """结构化过滤、关键词召回和来源丰富度重排。"""
    query = db.query(KnowledgeTimeSlice)
    session_match = re.search(r"(?:场次|session)\s*#?\s*(\d+)", question, re.IGNORECASE)
    if session_match:
        query = query.filter(KnowledgeTimeSlice.session_id == int(session_match.group(1)))
    candidates = query.order_by(KnowledgeTimeSlice.updated_at.desc()).limit(1000).all()
    terms = _query_terms(question)
    ranked: list[tuple[float, KnowledgeTimeSlice]] = []
    for row in candidates:
        haystack = (row.search_text or "").lower()
        lexical = sum(min(haystack.count(term), 5) * (1 + min(len(term), 4) / 4) for term in terms)
        anchor_bonus = 8 if row.anchor_name and row.anchor_name.lower() in question.lower() else 0
        source_bonus = min(3, int(bool(row.transcript_text)) + int(bool(row.comments_text)) + int(row.metric_point_count > 0))
        intent_bonus = min(2, row.high_intent_comment_count * 0.25)
        score = lexical + anchor_bonus + source_bonus + intent_bonus
        if score > 0 or not terms:
            ranked.append((score, row))
    ranked.sort(key=lambda item: (item[0], item[1].metric_point_count, item[1].updated_at), reverse=True)
    results = []
    for score, row in ranked[:limit]:
        source_types = []
        if row.transcript_text:
            source_types.append("直播话术")
        if row.comments_text:
            source_types.append("用户评论")
        if row.metric_point_count:
            source_types.append("分钟指标")
        excerpt = (row.transcript_text or row.comments_text or row.search_text or "")[:500]
        results.append({
            "id": row.id,
            "session_id": row.session_id,
            "anchor_name": row.anchor_name,
            "session_title": row.session_title,
            "slice_start_seconds": row.slice_start_seconds,
            "slice_end_seconds": row.slice_end_seconds,
            "time_range": f"{format_offset(row.slice_start_seconds)}-{format_offset(row.slice_end_seconds)}",
            "slice_start_time": row.slice_start_time,
            "slice_end_time": row.slice_end_time,
            "source_types": source_types,
            "excerpt": excerpt,
            "score": round(score, 2),
            "content": row.search_text,
            "comment_count": row.comment_count,
            "metric_point_count": row.metric_point_count,
        })
    KNOWLEDGE_SEARCH_TOTAL.labels(result="hit" if results else "miss").inc()
    return results
