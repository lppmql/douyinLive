"""直播场次的用户留资与钩子转化分析。

本模块只组合数据库中已经存在的真实评论、主播转写和客资记录。
规则无法证明因果关系，因此客资与钩子的关系统一标记为“时间窗关联”。
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from app.models.comments import Comment
from app.models.comment_user_profiles import CommentUserProfile
from app.models.leads import Lead
from app.models.live_sessions import LiveSession
from app.models.transcript_segments import TranscriptSegment


INTENT_TOPICS: dict[str, tuple[str, ...]] = {
    "选址": ("选址", "位置", "商圈", "人流", "小区", "学校", "商业街"),
    "预算": ("预算", "多少钱", "多少万", "租金", "房租", "转让费", "面积", "平方"),
    "品牌避坑": ("加盟", "品牌", "快招", "赵一鸣", "零食很忙", "好想来"),
    "供应链": ("货源", "供应链", "进货", "厂家", "配送", "选品"),
    "经营测算": ("毛利", "回本", "营业额", "利润", "损耗", "临期"),
    "资料领取": ("资料", "清单", "表格", "报告", "怎么领", "发我", "想要", "私信"),
}

HOOK_CONTENT_WORDS = ("资料", "清单", "表格", "报告", "名单", "计算表", "评估表", "避坑名单")
HOOK_ACTIONS: dict[str, tuple[str, ...]] = {
    "私信引导": (
        "后台", "私信", "站内消息", "站内发消息", "发消息", "给你发消息", "给你发个消息",
        "我给你发", "我给发个消息", "咨询我", "联系我", "联系客服",
    ),
    "领取动作": ("领取", "领取资料", "发资料", "资料发给你", "发给你", "给你发"),
    "按钮引导": ("红色按钮", "点击按钮", "点按钮", "左下角按钮", "右下角按钮"),
    "评论动作": ("评论区", "扣1", "打在公屏", "公屏打"),
}
HOOK_VALUE_WORDS = ("免费", "避坑", "解决", "分析", "评估", "帮你", "测算", "少走弯路")
FREE_ANALYSIS_WORDS = ("免费分析", "一对一", "帮你分析", "免费评估")


def _normalize_douyin_id(value: str | None) -> str:
    """仅做格式归一化，不把昵称或 sec_uid 冒充公开抖音号。"""
    return re.sub(r"[\s@]", "", value or "").casefold()


def _topics(text: str) -> list[str]:
    lowered = text.casefold()
    return [name for name, words in INTENT_TOPICS.items() if any(word.casefold() in lowered for word in words)]


def _classify_hook(text: str) -> dict[str, Any] | None:
    """按“资料内容、领取动作、资料价值”识别钩子及完整程度。"""
    lowered = text.casefold()
    has_content = any(word.casefold() in lowered for word in HOOK_CONTENT_WORDS)
    action_types = [
        name for name, words in HOOK_ACTIONS.items() if any(word.casefold() in lowered for word in words)
    ]
    has_value = any(word.casefold() in lowered for word in HOOK_VALUE_WORDS)
    has_free_analysis = any(word.casefold() in lowered for word in FREE_ANALYSIS_WORDS)
    # 只讲“资料/报告”但没有领取动作时属于钩子铺垫，不计入正式下钩子次数。
    direct_conversion_actions = [name for name in action_types if name != "评论动作"]
    # 单纯“打在公屏/评论区提问”属于互动，不算留资钩子；只有同时给出资料内容时才进入钩子。
    if not has_content and not direct_conversion_actions and not has_free_analysis:
        return None
    is_formal = bool(direct_conversion_actions or has_free_analysis or (has_content and "评论动作" in action_types))
    hook_types = []
    if has_content:
        hook_types.append("资料钩子")
    hook_types.extend(action_types)
    if has_free_analysis:
        hook_types.append("免费分析")
    element_count = sum((has_content, bool(action_types), has_value))
    strength = "strong" if element_count == 3 else "medium" if element_count == 2 else "weak"
    missing_elements = []
    if not has_content:
        missing_elements.append("具体资料")
    if not action_types:
        missing_elements.append("领取动作")
    if not has_value:
        missing_elements.append("资料价值")
    return {
        "hook_types": list(dict.fromkeys(hook_types)),
        "is_formal_hook": is_formal,
        "stage": "正式钩子" if is_formal else "钩子铺垫",
        "strength": strength,
        "missing_elements": missing_elements,
    }


def _contains_hook_value(text: str) -> bool:
    """判断片段是否只是在补充钩子的资料价值。"""
    lowered = text.casefold()
    return any(word.casefold() in lowered for word in HOOK_VALUE_WORDS)


def _relative_seconds(session: LiveSession, comment: Comment) -> float | None:
    if not session.live_start_time or not comment.comment_time:
        return None
    return max(0.0, (comment.comment_time - session.live_start_time).total_seconds())


def _recommendation(topics: list[str], has_lead: bool, hook_response: bool) -> str:
    if has_lead:
        return "已精确匹配客资，建议按用户关注主题继续跟进，避免重复索取联系方式。"
    if "资料领取" in topics:
        return "用户已经表达资料需求，先回答其核心问题，再明确说明对应资料价值和站内私信领取步骤。"
    if topics:
        topic = "、".join(topics[:2])
        action = "补充一个具体资料钩子" if not hook_response else "承接用户反馈并确认是否需要进一步分析"
        return f"围绕用户关注的{topic}先给出可执行答案，再{action}。"
    return "先用追问确认省份、预算、意向品牌和开店阶段，再匹配选址表、品牌名单或回本计算表。"


def build_session_conversion_analysis(
    db: Session,
    session: LiveSession,
    comments: list[Comment],
    total_comment_count: int | None = None,
) -> dict[str, Any]:
    """构建详情页所需的用户级分析、钩子时间轴和字段覆盖情况。"""
    segments = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.session_id == session.id, TranscriptSegment.asr_status == "completed")
        .order_by(TranscriptSegment.segment_start.asc(), TranscriptSegment.id.asc())
        .all()
    )
    # “已留资”是确认态，只允许使用已经由客资同步流程归属到本场的数据。
    # 未归属客资即使主播名和时间接近，也不能在用户卡片上显示为已留资。
    session_leads = (
        db.query(Lead)
        .filter(Lead.is_valid == 1, Lead.session_id == session.id, Lead.attribution_status == "matched")
        .order_by(Lead.create_time.asc(), Lead.id.asc())
        .all()
    )

    hooks: list[dict[str, Any]] = []
    for segment in segments:
        text = (segment.text_content or "").strip()
        classification = _classify_hook(text)
        if not text:
            continue
        # ASR 可能把“领取资料”和“帮你避坑”切成相邻两段。价值片段不能单独成钩子，
        # 但在 30 秒内紧跟已有候选时，应补入前一钩子的完整度与原话证据。
        if not classification:
            if (
                hooks
                and _contains_hook_value(text)
                and float(segment.segment_start or 0) - hooks[-1]["end_seconds"] <= 30
            ):
                previous = hooks[-1]
                previous["end_seconds"] = max(previous["end_seconds"], float(segment.segment_end or 0))
                previous["evidence_text"] = f'{previous["evidence_text"]} {text}'[:1000]
                previous["missing_elements"] = [
                    item for item in previous["missing_elements"] if item != "资料价值"
                ]
                combined_element_count = 3 - len(previous["missing_elements"])
                previous["strength"] = (
                    "strong" if combined_element_count == 3 else "medium" if combined_element_count == 2 else "weak"
                )
            continue
        event = {
                "id": int(segment.id),
                "start_seconds": float(segment.segment_start or 0),
                "end_seconds": float(segment.segment_end or segment.segment_start or 0),
                **classification,
                "evidence_text": text[:1000],
                "related_lead_count": 0,
                "comment_after_5m": 0,
                "comment_after_15m": 0,
                "comment_after_30m": 0,
                "lead_after_5m": 0,
                "lead_after_15m": 0,
                "lead_after_30m": 0,
                "high_intent_user_count": 0,
                "attribution_label": "时间窗关联，不代表确定因果",
            }
        # ASR 常把一句连续话术切成多个短片段。30 秒内连续命中的片段合并为一次钩子动作，
        # 避免把一句“私信领取资料”错误统计成多次转化动作。
        if hooks and event["start_seconds"] - hooks[-1]["end_seconds"] <= 30:
            previous = hooks[-1]
            previous["end_seconds"] = max(previous["end_seconds"], event["end_seconds"])
            previous["hook_types"] = list(dict.fromkeys([*previous["hook_types"], *event["hook_types"]]))
            previous["evidence_text"] = f'{previous["evidence_text"]} {event["evidence_text"]}'[:1000]
            previous["is_formal_hook"] = previous["is_formal_hook"] or event["is_formal_hook"]
            previous["stage"] = "正式钩子" if previous["is_formal_hook"] else "钩子铺垫"
            previous["missing_elements"] = [
                item for item in previous["missing_elements"] if item in event["missing_elements"]
            ]
            # 合并后的完整度可能高于任一单片段，必须按组合后的三要素重新计算强度。
            combined_element_count = 3 - len(previous["missing_elements"])
            previous["strength"] = (
                "strong" if combined_element_count == 3 else "medium" if combined_element_count == 2 else "weak"
            )
        else:
            hooks.append(event)

    formal_hooks = [hook for hook in hooks if hook["is_formal_hook"]]
    # 一条客资只关联到其产生前最近一次正式钩子；同时保留 5/15/30 分钟观察窗。
    for lead in session_leads:
        if not lead.create_time or not session.live_start_time:
            continue
        lead_seconds = (lead.create_time - session.live_start_time).total_seconds()
        for hook in formal_hooks:
            delta = lead_seconds - hook["end_seconds"]
            if 0 <= delta <= 300:
                hook["lead_after_5m"] += 1
            if 0 <= delta <= 900:
                hook["lead_after_15m"] += 1
            if 0 <= delta <= 1800:
                hook["lead_after_30m"] += 1
        candidates = [hook for hook in formal_hooks if 0 <= lead_seconds - hook["end_seconds"] <= 1800]
        if candidates:
            max(candidates, key=lambda item: item["end_seconds"])["related_lead_count"] += 1

    grouped: dict[str, list[Comment]] = defaultdict(list)
    for comment in comments:
        identity = comment.user_sec_uid or _normalize_douyin_id(comment.user_douyin_id) or (comment.user_nickname or "匿名用户")
        grouped[identity].append(comment)

    # 预计算评论时间和意向，避免每个钩子重复解析同一条评论文本。
    comment_samples = [
        (comment, seconds, bool(_topics(comment.comment_content or "")))
        for comment in comments
        if (seconds := _relative_seconds(session, comment)) is not None
    ]
    # 评论效果只统计真实评论时间；观察窗从钩子整句结束后开始。
    for hook in formal_hooks:
        intent_users: set[str] = set()
        for comment, seconds, has_intent in comment_samples:
            delta = seconds - hook["end_seconds"]
            if 0 <= delta <= 300:
                hook["comment_after_5m"] += 1
            if 0 <= delta <= 900:
                hook["comment_after_15m"] += 1
            if 0 <= delta <= 1800:
                hook["comment_after_30m"] += 1
            if 0 <= delta <= 300 and has_intent:
                intent_users.add(comment.user_sec_uid or comment.user_nickname or str(comment.id))
        hook["high_intent_user_count"] = len(intent_users)

    leads_by_douyin: dict[str, list[Lead]] = defaultdict(list)
    for lead in session_leads:
        normalized = _normalize_douyin_id(lead.douyin_id)
        if normalized:
            leads_by_douyin[normalized].append(lead)

    users: list[dict[str, Any]] = []
    sec_uids = {item.user_sec_uid for item in comments if item.user_sec_uid}
    cached_profiles = {
        item.sec_uid: item
        for item in db.query(CommentUserProfile)
        .filter(CommentUserProfile.sec_uid.in_(sec_uids))
        .all()
    } if sec_uids else {}
    for identity, rows in grouped.items():
        rows.sort(key=lambda item: (item.comment_time is None, item.comment_time, item.id))
        text = "\n".join((item.comment_content or "").strip() for item in rows)
        topics = _topics(text)
        sec_uid = next((item.user_sec_uid for item in rows if item.user_sec_uid), None)
        cached_profile = cached_profiles.get(sec_uid) if sec_uid else None
        public_id = (
            cached_profile.public_douyin_id
            if cached_profile and cached_profile.public_douyin_id
            else next((item.user_douyin_id for item in rows if item.user_douyin_id), None)
        )
        public_candidates = list(dict.fromkeys(filter(None, [
            public_id,
            cached_profile.unique_id if cached_profile else None,
            cached_profile.short_id if cached_profile else None,
        ])))
        matched_leads = []
        matched_id = None
        for candidate in public_candidates:
            candidate_leads = leads_by_douyin.get(_normalize_douyin_id(candidate), [])
            if candidate_leads:
                matched_id = candidate
                matched_leads.extend(candidate_leads)
                break
        comment_seconds = [value for item in rows if (value := _relative_seconds(session, item)) is not None]
        first_seconds = min(comment_seconds) if comment_seconds else None
        last_seconds = max(comment_seconds) if comment_seconds else None
        nearby_hooks = [
            hook
            for hook in formal_hooks
            if first_seconds is not None and first_seconds - 60 <= hook["start_seconds"] <= (last_seconds or first_seconds) + 300
        ]
        nearby_segments = [
            segment
            for segment in segments
            if first_seconds is not None
            and float(segment.segment_start or 0) >= first_seconds
            and float(segment.segment_start or 0) <= (last_seconds or first_seconds) + 180
            and set(_topics(segment.text_content or "")) & set(topics)
        ]
        high_intent = bool(topics) or any(int(item.is_high_intent or 0) == 1 for item in rows)
        users.append(
            {
                "identity_key": identity,
                "user_nickname": next((item.user_nickname for item in rows if item.user_nickname), None),
                "user_avatar_comment_id": next((int(item.id) for item in rows if item.user_avatar_url), None),
                "user_douyin_id": public_id,
                "user_unique_id": cached_profile.unique_id if cached_profile else None,
                "user_short_id": cached_profile.short_id if cached_profile else None,
                "douyin_id_type": cached_profile.douyin_id_type if cached_profile else None,
                "profile_status": (
                    cached_profile.fetch_status
                    if cached_profile else "pending"
                ),
                "comment_count": len(rows),
                "comments": [
                    {"id": int(item.id), "content": item.comment_content or "", "comment_time": item.comment_time}
                    for item in rows[-50:]
                ],
                "intent_topics": topics,
                "intent_level": "high" if "资料领取" in topics or matched_leads else "medium" if high_intent else "low",
                "has_lead": bool(matched_leads),
                "lead_match_method": (
                    "unique_id_exact" if matched_leads and cached_profile and matched_id == cached_profile.unique_id
                    else "short_id_exact" if matched_leads and cached_profile and matched_id == cached_profile.short_id
                    else "douyin_id_exact" if matched_leads else None
                ),
                "lead_time": matched_leads[0].create_time if matched_leads else None,
                "host_responded": bool(nearby_segments),
                "hook_action_detected": bool(nearby_hooks),
                "host_evidence": (nearby_segments[0].text_content or "")[:500] if nearby_segments else None,
                "related_hook_ids": [hook["id"] for hook in nearby_hooks],
                "recommendation": _recommendation(topics, bool(matched_leads), bool(nearby_hooks)),
            }
        )

    users.sort(key=lambda item: (not item["has_lead"], item["intent_level"] != "high", -item["comment_count"]))
    exact_lead_users = sum(1 for item in users if item["has_lead"])
    related_leads = sum(int(item["related_lead_count"]) for item in formal_hooks)
    avatar_count = sum(1 for item in users if item["user_avatar_comment_id"])
    douyin_count = sum(1 for item in users if item["user_douyin_id"])
    captured_comment_count = total_comment_count if total_comment_count is not None else len(comments)
    return {
        "summary": {
            "hook_count": len(formal_hooks),
            "effective_hook_count": sum(1 for item in formal_hooks if item["related_lead_count"] > 0),
            "strong_hook_count": sum(1 for item in formal_hooks if item["strength"] == "strong"),
            "incomplete_hook_count": sum(1 for item in formal_hooks if item["missing_elements"]),
            "session_lead_count": len(session_leads),
            "hook_window_lead_count": related_leads,
            "exact_matched_user_count": exact_lead_users,
            "comment_user_count": len(users),
        },
        "hook_events": hooks,
        "audience_users": users,
        "data_coverage": {
            "comment_count": captured_comment_count,
            "analysis_comment_count": len(comments),
            "analysis_truncated": captured_comment_count > len(comments),
            "comment_user_count": len(users),
            "avatar_user_count": avatar_count,
            "douyin_id_user_count": douyin_count,
            "transcript_segment_count": len(segments),
            "session_lead_count": len(session_leads),
            "avatar_coverage_percent": round(avatar_count * 100 / len(users), 1) if users else 0,
            "douyin_id_coverage_percent": round(douyin_count * 100 / len(users), 1) if users else 0,
        },
    }
