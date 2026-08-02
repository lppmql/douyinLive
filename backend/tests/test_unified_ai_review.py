"""统一 AI 复盘的事实约束、缓存和页面共用结果测试。"""

from datetime import datetime, timedelta
from unittest.mock import patch

from app.models.comments import Comment
from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.models.transcript_segments import TranscriptSegment
from app.services.ai.unified_review import generate_unified_review, overlay_user_analyses


def test_unified_review_uses_cache_and_keeps_business_facts(db):
    room = LiveRoom(account_name="AI复盘账号", anchor_name="主播甲", room_id_str="unified-review-room")
    db.add(room)
    db.flush()
    start = datetime(2026, 8, 2, 10, 0)
    session = LiveSession(
        room_id=room.id,
        anchor_name="主播甲",
        live_start_time=start,
        live_end_time=start + timedelta(hours=1),
        live_status="ended",
    )
    db.add(session)
    db.flush()
    comment = Comment(
        session_id=session.id,
        user_nickname="真实用户",
        user_sec_uid="sec-test-user",
        comment_content="我想开一家零食店，八十平需要多少预算？手机号13800138000，微信 wx:shop_owner88，加我 snack2026",
        comment_time=start + timedelta(minutes=5),
    )
    segment = TranscriptSegment(
        session_id=session.id,
        segment_start=310,
        segment_end=330,
        text_content="你在哪个城市？后台发预算，我把费用清单发给你，不要在公屏说13800138000。",
        asr_status="completed",
    )
    db.add_all([comment, segment])
    db.commit()
    rule_user = {
        "identity_key": "sec:sec-test-user",
        "user_nickname": "真实用户",
        "comments": [{"id": comment.id, "content": comment.comment_content, "comment_time": comment.comment_time}],
        "has_lead": False,
        "intent_topics": ["预算"],
        "intent_level": "high",
        "hook_action_detected": True,
        "recommendation": "规则建议",
    }
    calls = []

    def fake_chat(**kwargs):
        calls.append(kwargs["user_message"])
        if kwargs["operation"] == "audience_interaction_review":
            return __import__("json").dumps({"users": [{
                "user_index": 1,
                "business_stage": "preparing",
                "follow_up_status": "confirmed_lead",  # AI不得覆盖系统的未留资事实
                "demand_scope": "snack_store",
                "interaction_type": "high_intent",
                "precision_status": "precision_new_lead",
                "is_precision_lead": True,
                "host_response_status": "effective",
                "host_response_score": 86,
                "missed_opportunity": False,
                "recommendation": "继续追问城市和预算。",
                "suggested_reply": "先确认城市和面积，再给你预算清单。",
                "confidence": 0.9,
                "evidence": [{"evidence_id": f"C{comment.id}", "conclusion": "准备开店", "reason": "用户明确询问开店预算"}],
            }]}, ensure_ascii=False)
        return __import__("json").dumps({"summary": "本场有精准新客。", "strengths": ["主播有追问"], "problems": [], "next_actions": ["保持具体回答"]}, ensure_ascii=False)

    with patch("app.services.ai.unified_review.build_session_conversion_analysis", return_value={"audience_users": [rule_user]}), patch(
        "app.services.ai.unified_review.chat", side_effect=fake_chat
    ):
        first = generate_unified_review(db, session.id)
        second = generate_unified_review(db, session.id)

    assert len(calls) == 2
    model_prompt = calls[0]
    assert "13800138000" not in model_prompt
    assert "shop_owner88" not in model_prompt
    assert "snack2026" not in model_prompt
    assert "[手机号已脱敏]" in model_prompt
    assert "[微信号已脱敏]" in model_prompt
    assert "[疑似联系方式已脱敏]" in model_prompt
    assert first["summary"]["precision_new_lead_count"] == 1
    assert second["users"][0]["follow_up_status"] == "unknown"
    assert second["users"][0]["evidence"][0]["evidence_id"] == f"C{comment.id}"
    assert "13800138000" in second["users"][0]["evidence"][0]["text"]
    rule_user.update({
        "has_lead": True,
        "user_avatar_comment_id": comment.id,
        "user_douyin_id": "douyin-test-001",
        "profile_status": "success",
        "lead_contacts": [{"type": "phone", "value": "13800138000"}],
    })
    assert overlay_user_analyses(db, session.id, [rule_user])["status"] == "completed"
    assert rule_user["ai_analysis"]["is_precision_lead"] is True
    assert rule_user["ai_analysis"]["has_lead"] is True
    assert rule_user["ai_analysis"]["follow_up_status"] == "confirmed_lead"
    assert rule_user["ai_analysis"]["user_douyin_id"] == "douyin-test-001"
