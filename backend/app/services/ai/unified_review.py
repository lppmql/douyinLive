"""统一 AI 复盘：按用户分析评论与主播回应，再汇总整场结论。"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.comments import Comment
from app.models.comment_user_profiles import CommentUserProfile
from app.models.lead_conversion_pairs import LeadConversionPair
from app.models.live_sessions import LiveSession
from app.models.transcript_segments import TranscriptSegment
from app.models.unified_ai_review import AudienceInteractionAnalysis, UnifiedAiReviewRun
from app.services.ai.deepseek_client import chat
from app.services.analysis.session_conversion import build_session_conversion_analysis


ANALYSIS_VERSION = "audience-chain-v4"
MAX_USERS = 60
BATCH_SIZE = 1

BUSINESS_STAGES = {"preparing", "selecting_location", "comparing_brand", "opened_store", "suspected_paid", "unknown"}
FOLLOW_UP_STATUSES = {"not_lead", "confirmed_lead", "suspected_contacted", "unknown"}
DEMAND_SCOPES = {"snack_store", "non_snack_store", "industry_peer", "unknown"}
INTERACTION_TYPES = {"normal_inquiry", "high_intent", "rational_question", "malicious", "casual", "information_insufficient"}
PRECISION_STATUSES = {
    "precision_new_lead", "nurture", "existing_store", "in_follow_up", "existing_customer",
    "non_target", "industry_peer", "malicious", "information_insufficient",
}
RESPONSE_STATUSES = {"excellent", "effective", "average", "irrelevant", "no_response", "unknown"}
logger = logging.getLogger(__name__)
_LOCKS_GUARD = threading.Lock()
_SESSION_LOCKS: dict[int, threading.Lock] = {}


class AnalysisInputChangedError(RuntimeError):
    """分析期间真实输入发生变化，本轮结果必须丢弃。"""


class AnalysisGenerationBusyError(RuntimeError):
    """同场次已有有效生成租约。"""


SYSTEM_PROMPT = """
你是“零食店开店避坑知识科普直播”的复盘分析师。直播的目标是回答预算、选址、品牌、供应链等问题，再通过资料钩子引导用户主动站内私信留资。

必须遵守：
1. 只根据提供的真实评论和主播原话判断，不猜测。证据不足时选 unknown/information_insufficient。
2. confirmed_lead 是系统事实，不得修改。“已交钱”和“已联系拓展”如果只来自评论，必须使用 suspected 类结论，不得当成业务事实。
3. 质疑利润、预算、数据真实性属于 rational_question；只有持续辱骂、恶意刷屏且没有业务问题才是 malicious。
4. 精准新客必须是准备开零食店的新用户。已开店、疑似已交钱、疑似联系过拓展、非零食店需求、同行和恶意用户不计精准新客。
5. 主播回应必须与用户问题语义相关，不能因为时间接近就认定已回应。
6. 每个关键结论必须引用输入中的证据ID。建议话术不得虚假承诺收益。
7. 只输出 JSON，不输出 Markdown。
""".strip()


def _input_hash(
    comments: list[Comment],
    segments: list[TranscriptSegment],
    pairs: list[LeadConversionPair],
    profiles: list[CommentUserProfile],
) -> str:
    """只计算分析所需字段，联系方式明文不进入指纹或AI输入。"""
    payload = {
        "comments": [(
            row.id, row.comment_time.isoformat() if row.comment_time else None, row.comment_content,
            row.user_sec_uid, row.user_douyin_id, bool(row.is_high_intent),
            row.updated_at.isoformat() if row.updated_at else None,
        ) for row in sorted(comments, key=lambda item: item.id)],
        "segments": [(
            row.id, float(row.segment_start or 0), row.text_content,
            row.updated_at.isoformat() if row.updated_at else None,
        ) for row in sorted(segments, key=lambda item: item.id)],
        "pairs": [(
            row.id, row.douyin_lead_id, row.contact_lead_id, row.session_id, row.douyin_id,
            row.converted_at.isoformat() if row.converted_at else None, row.attribution_status,
            row.updated_at.isoformat() if row.updated_at else None,
        ) for row in sorted(pairs, key=lambda item: item.id)],
        "profiles": [(
            row.sec_uid, row.public_douyin_id, row.unique_id, row.short_id, row.fetch_status,
            row.updated_at.isoformat() if row.updated_at else None,
        ) for row in sorted(profiles, key=lambda item: item.sec_uid)],
        "version": ANALYSIS_VERSION,
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _nearby_transcripts(session: LiveSession, comments: list[dict[str, Any]], segments: list[TranscriptSegment]) -> list[dict[str, Any]]:
    if not session.live_start_time:
        return []
    ranges = []
    for comment in comments:
        value = comment.get("comment_time")
        if value:
            ranges.append(max(0, (value - session.live_start_time).total_seconds()))
    if not ranges:
        return []
    selected = []
    for segment in segments:
        start = float(segment.segment_start or 0)
        if any(second - 15 <= start <= second + 120 for second in ranges):
            selected.append({"id": f"T{segment.id}", "second": start, "text": (segment.text_content or "")[:500]})
    return selected[:12]


def _redact_for_ai(text: str, sensitive_values: set[str]) -> str:
    """模型输入统一脱敏；本地证据仍保留原文供页面核验。"""
    result = text or ""
    for value in sorted((value for value in sensitive_values if value), key=len, reverse=True):
        result = result.replace(value, "[联系方式已脱敏]")
    result = re.sub(r"(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d(?:[-\s]?\d){8}(?!\d)", "[手机号已脱敏]", result)
    result = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[邮箱已脱敏]", result)
    result = re.sub(
        r"(?i)(微信|微\s*信|wechat|vx|wx|v)\s*[:：号是加\-]*\s*[A-Za-z][-_A-Za-z0-9]{5,19}",
        lambda match: f"{match.group(1)}：[微信号已脱敏]",
        result,
    )
    result = re.sub(
        r"(?i)(加我|加一下|联系方式|私聊我|联系我)\s*[:：号是加\-]*\s*([A-Za-z][-_A-Za-z0-9]{5,19})",
        lambda match: f"{match.group(1)}：[疑似联系方式已脱敏]",
        result,
    )
    return result


def _load_analysis_inputs(
    db: Session, session_id: int
) -> tuple[list[Comment], list[TranscriptSegment], list[LeadConversionPair], list[CommentUserProfile]]:
    comments = db.query(Comment).filter(Comment.session_id == session_id).order_by(
        Comment.comment_time.desc(), Comment.id.desc()
    ).limit(2000).all()
    segments = db.query(TranscriptSegment).filter(
        TranscriptSegment.session_id == session_id,
        TranscriptSegment.asr_status == "completed",
    ).order_by(TranscriptSegment.segment_start.asc(), TranscriptSegment.id.asc()).limit(2000).all()
    pairs = db.query(LeadConversionPair).filter(LeadConversionPair.session_id == session_id).order_by(
        LeadConversionPair.id.asc()
    ).all()
    sec_uids = {row.user_sec_uid for row in comments if row.user_sec_uid}
    profiles = db.query(CommentUserProfile).filter(CommentUserProfile.sec_uid.in_(sec_uids)).order_by(
        CommentUserProfile.sec_uid.asc()
    ).all() if sec_uids else []
    return comments, segments, pairs, profiles


def _fresh_input_hash(db: Session, session_id: int) -> str:
    """使用独立短会话读取已提交业务数据，不干扰当前AI结果事务。"""
    if db.get_bind().dialect.name == "sqlite":
        return _input_hash(*_load_analysis_inputs(db, session_id))
    with Session(bind=db.get_bind()) as verify_db:
        return _input_hash(*_load_analysis_inputs(verify_db, session_id))


def _user_payload(
    index: int,
    user: dict[str, Any],
    session: LiveSession,
    segments: list[TranscriptSegment],
    sensitive_values: set[str],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    selected_comments = user.get("comments", [])[-12:]
    local_comments = [
        {"id": f"C{row['id']}", "time": row.get("comment_time").isoformat() if row.get("comment_time") else None, "text": row.get("content", "")[:300]}
        for row in selected_comments
    ]
    local_transcripts = _nearby_transcripts(session, selected_comments, segments)[:6]
    local_sources = {item["id"]: item for item in [*local_comments, *local_transcripts]}
    payload = {
        "user_index": index,
        "facts": {
            "confirmed_lead": bool(user.get("has_lead")),
            "intent_topics": user.get("intent_topics", []),
            "rule_intent_level": user.get("intent_level", "low"),
            "nearby_rule_hook": bool(user.get("hook_action_detected")),
        },
        "comments": [{**item, "text": _redact_for_ai(item["text"], sensitive_values)} for item in local_comments],
        "nearby_host_transcripts": [
            {**item, "text": _redact_for_ai(item["text"], sensitive_values)} for item in local_transcripts
        ],
    }
    return payload, local_sources


def _bounded(value: Any, allowed: set[str], fallback: str) -> str:
    return str(value) if str(value) in allowed else fallback


def _chat_json_with_retry(**kwargs) -> dict[str, Any]:
    """对模型偶发空响应做有限重试，不无限重试或伪造结果。"""
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            content = chat(
                **kwargs,
                response_format={"type": "json_object"},
                response_mode="text",
            )
            cleaned = content.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            parsed = json.loads(cleaned)
            if not isinstance(parsed, dict):
                raise ValueError("AI未返回JSON对象")
            return parsed
        except Exception as exc:
            last_error = exc
            logger.warning("统一AI复盘调用失败，尝试=%s 错误=%s", attempt + 1, type(exc).__name__)
    assert last_error is not None
    raise last_error


def _normalize_result(
    item: dict[str, Any],
    user: dict[str, Any],
    input_payload: dict[str, Any],
    local_sources: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    confirmed_lead = bool(user.get("has_lead"))
    follow_up = "confirmed_lead" if confirmed_lead else _bounded(item.get("follow_up_status"), FOLLOW_UP_STATUSES, "unknown")
    if not confirmed_lead and follow_up == "confirmed_lead":
        follow_up = "unknown"
    score = item.get("host_response_score")
    score = max(0, min(100, int(score))) if isinstance(score, (int, float)) else None
    confidence = item.get("confidence", 0)
    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence = 0.0
    evidence = []
    evidence_sources = {
        source["id"]: source
        for source in [*input_payload.get("comments", []), *input_payload.get("nearby_host_transcripts", [])]
    }
    for evidence_item in item.get("evidence", [])[:8]:
        if not isinstance(evidence_item, dict):
            continue
        evidence_id = str(evidence_item.get("evidence_id", ""))
        if evidence_id in evidence_sources:
            source = local_sources[evidence_id]
            evidence.append({
                "evidence_id": evidence_id,
                "conclusion": str(evidence_item.get("conclusion", ""))[:200],
                "reason": str(evidence_item.get("reason", ""))[:500],
                "text": str(source.get("text", ""))[:500],
                "time": source.get("time"),
                "second": source.get("second"),
            })
    # 某些模型会遗漏 evidence 数组。此时只附加实际发送给模型的原文作为
    # “分析输入证据”，并下调置信度，不声称该原文已独立证明AI结论。
    if not evidence:
        fallback_sources = [
            *[local_sources[item["id"]] for item in input_payload.get("comments", [])[-1:]],
            *[local_sources[item["id"]] for item in input_payload.get("nearby_host_transcripts", [])[:1]],
        ]
        for source in fallback_sources:
            evidence.append({
                "evidence_id": source["id"],
                "conclusion": "AI分析输入证据",
                "reason": "模型未返回细分引用，该原文是本结论的真实输入，建议人工复核。",
                "text": str(source.get("text", ""))[:500],
                "time": source.get("time"),
                "second": source.get("second"),
            })
        confidence = min(confidence, 0.6)
    precision_status = _bounded(item.get("precision_status"), PRECISION_STATUSES, "information_insufficient")
    is_precision = bool(item.get("is_precision_lead")) and precision_status == "precision_new_lead"
    return {
        "business_stage": _bounded(item.get("business_stage"), BUSINESS_STAGES, "unknown"),
        "follow_up_status": follow_up,
        "demand_scope": _bounded(item.get("demand_scope"), DEMAND_SCOPES, "unknown"),
        "interaction_type": _bounded(item.get("interaction_type"), INTERACTION_TYPES, "information_insufficient"),
        "precision_status": precision_status,
        "is_precision_lead": is_precision,
        "exclusion_reason": str(item.get("exclusion_reason") or "")[:1000] or None,
        "host_response_status": _bounded(item.get("host_response_status"), RESPONSE_STATUSES, "unknown"),
        "host_response_score": score,
        "missed_opportunity": bool(item.get("missed_opportunity")),
        "recommendation": str(item.get("recommendation") or user.get("recommendation") or "证据不足，建议先追问开店阶段与具体需求。")[:2000],
        "suggested_reply": str(item.get("suggested_reply") or "")[:2000] or None,
        "confidence": confidence,
        "evidence": evidence,
    }


def _serialize_analysis(row: AudienceInteractionAnalysis) -> dict[str, Any]:
    result = {
        "id": row.id,
        "identity_key": row.identity_key,
        "user_nickname": row.user_nickname,
        "business_stage": row.business_stage,
        "follow_up_status": row.follow_up_status,
        "demand_scope": row.demand_scope,
        "interaction_type": row.interaction_type,
        "precision_status": row.precision_status,
        "is_precision_lead": bool(row.is_precision_lead),
        "exclusion_reason": row.exclusion_reason,
        "host_response_status": row.host_response_status,
        "host_response_score": row.host_response_score,
        "missed_opportunity": bool(row.missed_opportunity),
        "recommendation": row.recommendation,
        "suggested_reply": row.suggested_reply,
        "confidence": float(row.confidence or 0),
        "evidence": row.evidence or [],
    }
    if row.manual_override:
        result.update(row.manual_override)
        # 留资状态只由系统配对事实产生，人工结论和历史脏数据均不得覆盖。
        result["follow_up_status"] = row.follow_up_status
        result["manual_confirmed"] = True
    else:
        result["manual_confirmed"] = False
    return result


def _enrich_user_business_facts(
    db: Session,
    session_id: int,
    serialized_users: list[dict[str, Any]],
    business_users: list[dict[str, Any]] | None = None,
) -> None:
    """把公开资料和系统留资事实合并到AI结果，两个页面共用同一展示口径。"""
    if not serialized_users:
        return
    if business_users is None:
        comments = db.query(Comment).filter(Comment.session_id == session_id).order_by(
            Comment.comment_time.desc(), Comment.id.desc()
        ).limit(2000).all()
        grouped: dict[str, list[Comment]] = defaultdict(list)
        for comment in comments:
            public_id = re.sub(r"[\s@]", "", comment.user_douyin_id or "").casefold()
            identity = comment.user_sec_uid or public_id or (comment.user_nickname or "匿名用户")
            grouped[identity].append(comment)
        sec_uids = {row.user_sec_uid for row in comments if row.user_sec_uid}
        profiles = {
            row.sec_uid: row for row in db.query(CommentUserProfile)
            .filter(CommentUserProfile.sec_uid.in_(sec_uids)).all()
        } if sec_uids else {}
        pairs = db.query(LeadConversionPair).filter(
            LeadConversionPair.session_id == session_id,
            LeadConversionPair.attribution_status == "attributed",
        ).order_by(LeadConversionPair.converted_at.asc(), LeadConversionPair.id.asc()).all()
        pairs_by_id: dict[str, list[LeadConversionPair]] = defaultdict(list)
        for pair in pairs:
            normalized = re.sub(r"[\s@]", "", pair.douyin_id or "").casefold()
            if normalized:
                pairs_by_id[normalized].append(pair)
        business_users = []
        for identity, rows in grouped.items():
            profile = next((profiles[row.user_sec_uid] for row in rows if row.user_sec_uid in profiles), None)
            public_id = (
                profile.public_douyin_id if profile and profile.public_douyin_id
                else next((row.user_douyin_id for row in rows if row.user_douyin_id), None)
            )
            candidates = list(dict.fromkeys(filter(None, [
                public_id,
                profile.unique_id if profile else None,
                profile.short_id if profile else None,
            ])))
            matched: list[LeadConversionPair] = []
            matched_id = None
            for candidate in candidates:
                matched = pairs_by_id.get(re.sub(r"[\s@]", "", candidate).casefold(), [])
                if matched:
                    matched_id = candidate
                    break
            business_users.append({
                "identity_key": identity,
                "user_avatar_comment_id": next((row.id for row in rows if row.user_avatar_url), None),
                "user_douyin_id": public_id,
                "douyin_id_type": profile.douyin_id_type if profile else None,
                "profile_status": profile.fetch_status if profile else "pending",
                "has_lead": bool(matched),
                "lead_match_method": (
                    "unique_id_exact" if matched and profile and matched_id == profile.unique_id
                    else "short_id_exact" if matched and profile and matched_id == profile.short_id
                    else "douyin_id_exact" if matched else None
                ),
                "lead_time": matched[0].converted_at if matched else None,
                "lead_contacts": [{
                    "type": row.contact_type,
                    "value": row.contact_value,
                    "converted_at": row.converted_at,
                    "gap_seconds": row.gap_seconds,
                } for row in matched],
            })
    facts_by_identity = {item["identity_key"]: item for item in business_users}
    for user in serialized_users:
        facts = facts_by_identity.get(user["identity_key"], {})
        has_lead = bool(facts.get("has_lead"))
        user.update({
            "user_avatar_comment_id": facts.get("user_avatar_comment_id"),
            "user_douyin_id": facts.get("user_douyin_id"),
            "douyin_id_type": facts.get("douyin_id_type"),
            "profile_status": facts.get("profile_status", "pending"),
            "has_lead": has_lead,
            "lead_contacts": facts.get("lead_contacts", []),
            "lead_match_method": facts.get("lead_match_method"),
            "lead_time": facts.get("lead_time"),
        })
        # 确认留资只能来自实时系统配对事实；AI历史结果不得与页面标识冲突。
        if has_lead:
            user["follow_up_status"] = "confirmed_lead"
        elif user.get("follow_up_status") == "confirmed_lead":
            user["follow_up_status"] = "unknown"


def get_unified_review(
    db: Session,
    session_id: int,
    business_users: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    run = db.query(UnifiedAiReviewRun).filter(UnifiedAiReviewRun.session_id == session_id).first()
    if not run:
        return None
    rows = db.query(AudienceInteractionAnalysis).filter(
        AudienceInteractionAnalysis.session_id == session_id
    ).order_by(AudienceInteractionAnalysis.is_precision_lead.desc(), AudienceInteractionAnalysis.id.asc()).all()
    serialized_users = [_serialize_analysis(row) for row in rows]
    _enrich_user_business_facts(db, session_id, serialized_users, business_users)
    comment_ids: set[int] = set()
    segment_ids: set[int] = set()
    for user in serialized_users:
        for evidence in user["evidence"]:
            evidence_id = str(evidence.get("evidence_id", ""))
            if evidence_id[1:].isdigit():
                if evidence_id.startswith("C"):
                    comment_ids.add(int(evidence_id[1:]))
                elif evidence_id.startswith("T"):
                    segment_ids.add(int(evidence_id[1:]))
    comments_by_id = {row.id: row for row in db.query(Comment).filter(
        Comment.session_id == session_id, Comment.id.in_(comment_ids)
    ).all()} if comment_ids else {}
    segments_by_id = {
        row.id: row for row in db.query(TranscriptSegment).filter(
            TranscriptSegment.session_id == session_id, TranscriptSegment.id.in_(segment_ids)
        ).all()
    } if segment_ids else {}
    for user in serialized_users:
        for evidence in user["evidence"]:
            evidence_id = str(evidence.get("evidence_id", ""))
            numeric_id = int(evidence_id[1:]) if evidence_id[1:].isdigit() else 0
            if evidence_id.startswith("C") and numeric_id in comments_by_id:
                source = comments_by_id[numeric_id]
                evidence.setdefault("text", source.comment_content or "")
                evidence.setdefault("time", source.comment_time.isoformat() if source.comment_time else None)
            elif evidence_id.startswith("T") and numeric_id in segments_by_id:
                source = segments_by_id[numeric_id]
                evidence.setdefault("text", source.text_content or "")
                evidence.setdefault("second", float(source.segment_start or 0))
    current_inputs = _load_analysis_inputs(db, session_id)
    stale = run.analysis_version != ANALYSIS_VERSION or run.input_hash != _input_hash(*current_inputs)
    return {
        "status": "stale" if run.status == "completed" and stale else run.status,
        "analysis_version": run.analysis_version,
        "model_name": run.model_name,
        "input_hash": run.input_hash,
        "summary": run.summary or {},
        "analyzed_user_count": run.analyzed_user_count,
        "completed_at": run.completed_at,
        "error_message": run.error_message,
        "users": serialized_users,
    }


def overlay_user_analyses(db: Session, session_id: int, users: list[dict[str, Any]]) -> dict[str, Any] | None:
    """将已保存 AI 结果叠加到详情页用户，不在 GET 请求中调用模型。"""
    review = get_unified_review(db, session_id, users)
    if not review:
        return None
    by_identity = {item["identity_key"]: item for item in review["users"]}
    for user in users:
        user["ai_analysis"] = by_identity.get(user["identity_key"])
    return {key: value for key, value in review.items() if key != "users"}


def refresh_unified_summary_counts(db: Session, session_id: int) -> None:
    """人工纠正后刷新分类数，保留原有整场AI文字结论。"""
    run = db.query(UnifiedAiReviewRun).filter(UnifiedAiReviewRun.session_id == session_id).first()
    if not run:
        return
    values = [_serialize_analysis(row) for row in db.query(AudienceInteractionAnalysis).filter(
        AudienceInteractionAnalysis.session_id == session_id
    ).all()]
    summary = dict(run.summary or {})
    summary.update({
        "precision_new_lead_count": sum(1 for item in values if item["is_precision_lead"]),
        "precision_unconverted_count": sum(
            1 for item in values if item["is_precision_lead"] and item["follow_up_status"] != "confirmed_lead"
        ),
        "opened_store_count": sum(1 for item in values if item["business_stage"] == "opened_store"),
        "suspected_paid_count": sum(1 for item in values if item["business_stage"] == "suspected_paid"),
        "suspected_contacted_count": sum(1 for item in values if item["follow_up_status"] == "suspected_contacted"),
        "non_target_count": sum(1 for item in values if item["demand_scope"] == "non_snack_store"),
        "rational_question_count": sum(1 for item in values if item["interaction_type"] == "rational_question"),
        "malicious_count": sum(1 for item in values if item["interaction_type"] == "malicious"),
        "missed_opportunity_count": sum(1 for item in values if item["missed_opportunity"]),
    })
    run.summary = summary
    db.commit()


def generate_unified_review(db: Session, session_id: int, *, force: bool = False) -> dict[str, Any]:
    """同一进程内同一场次只允许一个生成任务，避免手动与自动任务重复扣费。"""
    with _LOCKS_GUARD:
        lock = _SESSION_LOCKS.setdefault(session_id, threading.Lock())
    with lock:
        return _generate_unified_review(db, session_id, force=force)


def _generate_unified_review(db: Session, session_id: int, *, force: bool = False) -> dict[str, Any]:
    """生成或复用一场直播的统一 AI 复盘，模型输入不包含联系方式。"""
    session = db.get(LiveSession, session_id)
    if not session:
        raise ValueError("直播场次不存在")
    comments, segments, pairs, profiles = _load_analysis_inputs(db, session_id)
    fingerprint = _input_hash(comments, segments, pairs, profiles)
    run = db.query(UnifiedAiReviewRun).filter(UnifiedAiReviewRun.session_id == session_id).first()
    if run and not force and run.status == "completed" and run.input_hash == fingerprint and run.analysis_version == ANALYSIS_VERSION:
        return get_unified_review(db, session_id) or {}
    if not run:
        run = UnifiedAiReviewRun(session_id=session_id, analysis_version=ANALYSIS_VERSION, summary={})
        db.add(run)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        run = db.query(UnifiedAiReviewRun).filter(UnifiedAiReviewRun.session_id == session_id).first()
    assert run is not None
    lease_token = str(uuid.uuid4())
    now = datetime.utcnow()
    claimed = db.query(UnifiedAiReviewRun).filter(
        UnifiedAiReviewRun.id == run.id,
        or_(
            UnifiedAiReviewRun.status != "running",
            UnifiedAiReviewRun.lease_expires_at.is_(None),
            UnifiedAiReviewRun.lease_expires_at < now,
        ),
    ).update({
        UnifiedAiReviewRun.status: "running",
        UnifiedAiReviewRun.input_hash: fingerprint,
        UnifiedAiReviewRun.analysis_version: ANALYSIS_VERSION,
        UnifiedAiReviewRun.model_name: settings.DEEPSEEK_MODEL,
        UnifiedAiReviewRun.error_message: None,
        UnifiedAiReviewRun.generation_token: lease_token,
        UnifiedAiReviewRun.lease_expires_at: now + timedelta(hours=2),
    }, synchronize_session=False)
    db.commit()
    if claimed != 1:
        raise AnalysisGenerationBusyError("同场次AI复盘正在运行，请稍后重试")
    run = db.query(UnifiedAiReviewRun).filter(UnifiedAiReviewRun.id == run.id).first()
    assert run is not None

    conversion = build_session_conversion_analysis(db, session, comments, len(comments))
    users = conversion["audience_users"][:MAX_USERS]
    indexed_users = list(enumerate(users, start=1))
    normalized_results: dict[str, dict[str, Any]] = {}
    try:
        for offset in range(0, len(indexed_users), BATCH_SIZE):
            batch = indexed_users[offset:offset + BATCH_SIZE]
            sensitive_values = {row.contact_value for row in pairs if row.contact_value}
            prepared = [_user_payload(index, user, session, segments, sensitive_values) for index, user in batch]
            payload = [item[0] for item in prepared]
            local_sources_by_index = {index: item[1] for (index, _user), item in zip(batch, prepared)}
            result = _chat_json_with_retry(
                system_prompt=SYSTEM_PROMPT,
                user_message=(
                    "分析以下用户互动。返回 {\"users\":[...]}，每项包含 user_index、business_stage、"
                    "follow_up_status、demand_scope、interaction_type、precision_status、is_precision_lead、"
                    "exclusion_reason、host_response_status、host_response_score、missed_opportunity、"
                    "recommendation、suggested_reply、confidence、evidence。evidence每个用户至少1条，且evidence_id必须引用输入的C/T编号。\n"
                    "回答务必简洁，避免重复评论原文，确保JSON完整闭合。\n"
                    + json.dumps(payload, ensure_ascii=False)
                ),
                temperature=0.2,
                max_tokens=8000,
                operation="audience_interaction_review",
                session_id=session_id,
                prompt_name="unified_audience_review",
                prompt_version=1,
            )
            by_index = {int(item.get("user_index", 0)): item for item in result.get("users", []) if isinstance(item, dict)}
            payload_by_index = {int(item["user_index"]): item for item in payload}
            for index, user in batch:
                normalized_results[user["identity_key"]] = _normalize_result(
                    by_index.get(index, {}), user, payload_by_index[index], local_sources_by_index[index]
                )

        if _fresh_input_hash(db, session_id) != fingerprint:
            raise AnalysisInputChangedError("分析期间输入数据已更新，请重新生成")

        existing = {row.identity_key: row for row in db.query(AudienceInteractionAnalysis).filter(
            AudienceInteractionAnalysis.session_id == session_id
        ).all()}
        retained = set(normalized_results)
        for identity_key, data in normalized_results.items():
            row = existing.get(identity_key)
            if row is None:
                row = AudienceInteractionAnalysis(run_id=run.id, session_id=session_id, identity_key=identity_key)
                db.add(row)
            row.run_id = run.id
            row.user_nickname = next(
                (user.get("user_nickname") for user in users if user["identity_key"] == identity_key),
                None,
            )
            for key, value in data.items():
                if key == "confidence":
                    value = Decimal(str(value))
                elif key in {"is_precision_lead", "missed_opportunity"}:
                    value = int(bool(value))
                setattr(row, key, value)
        for identity_key, row in existing.items():
            if identity_key not in retained:
                db.delete(row)
        db.flush()

        values = list(normalized_results.values())
        users_by_identity = {user["identity_key"]: user for user in users}
        counters = {
            "precision_new_lead_count": sum(1 for item in values if item["is_precision_lead"]),
            "confirmed_lead_count": sum(1 for user in users if user.get("has_lead")),
            "precision_unconverted_count": sum(
                1 for identity_key, item in normalized_results.items()
                if item["is_precision_lead"] and not users_by_identity[identity_key].get("has_lead")
            ),
            "opened_store_count": sum(1 for item in values if item["business_stage"] == "opened_store"),
            "suspected_paid_count": sum(1 for item in values if item["business_stage"] == "suspected_paid"),
            "suspected_contacted_count": sum(1 for item in values if item["follow_up_status"] == "suspected_contacted"),
            "non_target_count": sum(1 for item in values if item["demand_scope"] == "non_snack_store"),
            "rational_question_count": sum(1 for item in values if item["interaction_type"] == "rational_question"),
            "malicious_count": sum(1 for item in values if item["interaction_type"] == "malicious"),
            "missed_opportunity_count": sum(1 for item in values if item["missed_opportunity"]),
        }
        response_counts = Counter(item["host_response_status"] for item in values)
        compact = [{
            "precision_status": item["precision_status"],
            "host_response_status": item["host_response_status"],
            "missed_opportunity": item["missed_opportunity"],
            "recommendation": item["recommendation"],
        } for item in values]
        summary_ai = _chat_json_with_retry(
            system_prompt=SYSTEM_PROMPT,
            user_message=(
                "根据已完成的用户分析汇总整场复盘。返回JSON：summary、strengths(最多3条)、problems(最多5条)、"
                "next_actions(最多5条)。这一步只能综合给定的计数、分类和建议，不得新增用户事实、人数或因果结论；"
                "输出文字属于AI综合建议，不是新的事实证据。\n"
                + json.dumps({"counts": counters, "users": compact}, ensure_ascii=False)
            ),
            temperature=0.2,
            max_tokens=5000,
            operation="unified_session_review_summary",
            session_id=session_id,
            prompt_name="unified_session_review_summary",
            prompt_version=1,
        ) if values else {"summary": "本场暂无可分析的用户互动。", "strengths": [], "problems": [], "next_actions": []}
        if _fresh_input_hash(db, session_id) != fingerprint:
            raise AnalysisInputChangedError("整场汇总期间输入数据已更新，请重新生成")
        completed_at = datetime.utcnow()
        completed = db.query(UnifiedAiReviewRun).filter(
            UnifiedAiReviewRun.id == run.id,
            UnifiedAiReviewRun.generation_token == lease_token,
            UnifiedAiReviewRun.input_hash == fingerprint,
        ).update({
            UnifiedAiReviewRun.summary: {
            **counters,
            "response_counts": dict(response_counts),
            "summary": str(summary_ai.get("summary", ""))[:3000],
            "strengths": [str(item)[:500] for item in summary_ai.get("strengths", [])[:3]],
            "problems": [str(item)[:500] for item in summary_ai.get("problems", [])[:5]],
            "next_actions": [str(item)[:500] for item in summary_ai.get("next_actions", [])[:5]],
            },
            UnifiedAiReviewRun.status: "completed",
            UnifiedAiReviewRun.analyzed_user_count: len(values),
            UnifiedAiReviewRun.completed_at: completed_at,
            UnifiedAiReviewRun.generation_token: None,
            UnifiedAiReviewRun.lease_expires_at: None,
        }, synchronize_session=False)
        if completed != 1:
            raise RuntimeError("AI复盘任务租约已失效，请重新生成")
        db.commit()
        return get_unified_review(db, session_id) or {}
    except Exception as exc:
        db.rollback()
        failure_status = "stale" if isinstance(exc, AnalysisInputChangedError) else "failed"
        failure_message = (
            "分析期间数据已更新，请重新生成"
            if isinstance(exc, AnalysisInputChangedError)
            else f"{type(exc).__name__}: AI分析失败，可重试"
        )[:500]
        db.query(UnifiedAiReviewRun).filter(
            UnifiedAiReviewRun.session_id == session_id,
            UnifiedAiReviewRun.generation_token == lease_token,
        ).update({
            UnifiedAiReviewRun.status: failure_status,
            UnifiedAiReviewRun.error_message: failure_message,
            UnifiedAiReviewRun.generation_token: None,
            UnifiedAiReviewRun.lease_expires_at: None,
        }, synchronize_session=False)
        db.commit()
        raise
