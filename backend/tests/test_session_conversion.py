"""用户留资与钩子转化分析测试。"""

from datetime import datetime, timedelta

from app.models.comments import Comment
from app.models.comment_user_profiles import CommentUserProfile
from app.models.leads import Lead
from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.models.transcript_segments import TranscriptSegment
from app.services.analysis.session_conversion import build_session_conversion_analysis
from app.services.leads.lead_pairing import rebuild_lead_conversion_pairs


def _session(db):
    start = datetime(2026, 8, 1, 10, 0)
    room = LiveRoom(account_name="测试账号", anchor_name="测试主播", room_id_str="conversion-room")
    db.add(room)
    db.flush()
    session = LiveSession(
        room_id=room.id,
        anchor_name="测试主播",
        live_start_time=start,
        live_end_time=start + timedelta(hours=1),
        live_duration_seconds=3600,
        live_status="finished",
    )
    db.add(session)
    db.flush()
    return session


def _add_confirmed_lead_pair(db, session, douyin_id: str, minute: int, external_id: int):
    """测试也遵守真实口径：同主播60秒内抖音号和联系方式成对出现。"""
    db.add_all([
        Lead(
            session_id=session.id,
            douyin_id=douyin_id,
            anchor_name="测试主播",
            external_source="test",
            external_id=external_id,
            attribution_status="matched",
            create_time=session.live_start_time + timedelta(minutes=minute),
        ),
        Lead(
            session_id=session.id,
            lead_phone="13800138000",
            anchor_name="测试主播",
            external_source="test",
            external_id=external_id + 1,
            attribution_status="matched",
            create_time=session.live_start_time + timedelta(minutes=minute, seconds=20),
        ),
    ])
    db.flush()
    rebuild_lead_conversion_pairs(db)


def test_exact_douyin_id_marks_user_as_lead_and_attributes_nearest_hook(db):
    session = _session(db)
    comment = Comment(
        session_id=session.id,
        user_nickname="准备开店",
        user_douyin_id="Shop_123",
        user_sec_uid="stable-user",
        comment_content="预算二十万，想要选址评估表",
        comment_time=session.live_start_time + timedelta(minutes=10),
    )
    db.add(comment)
    db.add(
        TranscriptSegment(
            session_id=session.id,
            segment_start=650,
            segment_end=660,
            text_content="需要选址评估表的可以站内私信领取，我帮你免费分析。",
            asr_status="completed",
        )
    )
    _add_confirmed_lead_pair(db, session, "@shop_123 ", 15, 1)
    db.commit()

    result = build_session_conversion_analysis(db, session, [comment])

    assert result["summary"]["hook_count"] == 1
    assert result["summary"]["hook_window_lead_count"] == 1
    assert result["audience_users"][0]["has_lead"] is True
    assert result["audience_users"][0]["lead_match_method"] == "douyin_id_exact"
    assert result["audience_users"][0]["hook_action_detected"] is True


def test_nickname_or_sec_uid_never_fakes_lead_match(db):
    session = _session(db)
    comment = Comment(
        session_id=session.id,
        user_nickname="同名用户",
        user_sec_uid="secret-stable-id",
        comment_content="想开店",
        comment_time=session.live_start_time + timedelta(minutes=5),
    )
    db.add_all(
        [
            comment,
            Lead(
                session_id=session.id,
                lead_name="同名用户",
                douyin_id="secret-stable-id",
                external_source="test",
                external_id=2,
                attribution_status="matched",
                create_time=session.live_start_time + timedelta(minutes=6),
            ),
        ]
    )
    db.commit()

    result = build_session_conversion_analysis(db, session, [comment])

    assert result["audience_users"][0]["has_lead"] is False
    assert result["summary"]["exact_matched_user_count"] == 0


def test_cached_short_id_can_exactly_match_lead_while_unique_id_is_displayed(db):
    """自定义号用于展示时，数字短号仍可作为独立精确匹配依据。"""
    session = _session(db)
    comment = Comment(
        session_id=session.id,
        user_nickname="双号码用户",
        user_sec_uid="stable-both-id-user",
        user_douyin_id="custom_public_id",
        comment_content="想领取选址表",
        comment_time=session.live_start_time + timedelta(minutes=5),
    )
    db.add_all([
        comment,
        CommentUserProfile(
            sec_uid="stable-both-id-user",
            unique_id="custom_public_id",
            short_id="123456789",
            public_douyin_id="custom_public_id",
            douyin_id_type="unique_id",
            fetch_status="success",
        ),
    ])
    db.flush()
    _add_confirmed_lead_pair(db, session, "123456789", 6, 22)
    db.commit()

    result = build_session_conversion_analysis(db, session, [comment])
    user = result["audience_users"][0]

    assert user["user_douyin_id"] == "custom_public_id"
    assert user["has_lead"] is True
    assert user["lead_match_method"] == "short_id_exact"


def test_pending_lead_is_not_counted_as_confirmed_even_when_time_matches(db):
    session = _session(db)
    db.add(
        Lead(
            session_id=None,
            douyin_id="same-time-user",
            anchor_name="另一个主播",
            external_source="test",
            external_id=3,
            attribution_status="pending",
            create_time=session.live_start_time + timedelta(minutes=10),
        )
    )
    db.commit()

    result = build_session_conversion_analysis(db, session, [])

    assert result["summary"]["session_lead_count"] == 0


def test_adjacent_asr_segments_are_one_hook_action(db):
    session = _session(db)
    db.add_all(
        [
            TranscriptSegment(
                session_id=session.id,
                segment_start=100,
                segment_end=110,
                text_content="我准备了选址评估表。",
                asr_status="completed",
            ),
            TranscriptSegment(
                session_id=session.id,
                segment_start=112,
                segment_end=120,
                text_content="站内私信我领取资料。",
                asr_status="completed",
            ),
        ]
    )
    db.commit()

    result = build_session_conversion_analysis(db, session, [])

    assert result["summary"]["hook_count"] == 1
    assert result["hook_events"][0]["hook_types"] == ["资料钩子", "私信引导", "领取动作"]
    assert result["hook_events"][0]["stage"] == "正式钩子"


def test_business_phrases_are_formal_hooks_and_content_only_is_lead_in(db):
    session = _session(db)
    phrases = ["去后台看一下", "我给你发个消息", "点击红色按钮", "我给你发资料"]
    segments = [
        TranscriptSegment(
            session_id=session.id,
            segment_start=index * 100,
            segment_end=index * 100 + 10,
            text_content=text,
            asr_status="completed",
        )
        for index, text in enumerate(["这里有一份行业报告", *phrases], start=1)
    ]
    db.add_all(segments)
    db.commit()

    result = build_session_conversion_analysis(db, session, [])

    assert result["summary"]["hook_count"] == len(phrases)
    assert result["hook_events"][0]["stage"] == "钩子铺垫"
    assert all(item["is_formal_hook"] for item in result["hook_events"][1:])


def test_adjacent_content_and_action_recalculate_combined_strength(db):
    session = _session(db)
    db.add_all(
        [
            TranscriptSegment(
                session_id=session.id,
                segment_start=100,
                segment_end=110,
                text_content="这里有一份品牌名单。",
                asr_status="completed",
            ),
            TranscriptSegment(
                session_id=session.id,
                segment_start=120,
                segment_end=130,
                text_content="去后台私信我。",
                asr_status="completed",
            ),
        ]
    )
    db.commit()

    result = build_session_conversion_analysis(db, session, [])

    assert result["hook_events"][0]["strength"] == "medium"
    assert result["hook_events"][0]["missing_elements"] == ["资料价值"]


def test_value_only_segment_supplements_previous_hook_without_becoming_standalone(db):
    session = _session(db)
    db.add_all(
        [
            TranscriptSegment(
                session_id=session.id,
                segment_start=100,
                segment_end=110,
                text_content="点击红色按钮领取选址评估表。",
                asr_status="completed",
            ),
            TranscriptSegment(
                session_id=session.id,
                segment_start=120,
                segment_end=130,
                text_content="可以帮你避坑、少走弯路。",
                asr_status="completed",
            ),
        ]
    )
    db.commit()

    result = build_session_conversion_analysis(db, session, [])

    assert result["summary"]["hook_count"] == 1
    assert result["hook_events"][0]["strength"] == "strong"
    assert result["hook_events"][0]["missing_elements"] == []


def test_hook_effect_windows_use_real_comments_and_matched_leads(db):
    session = _session(db)
    db.add(
        TranscriptSegment(
            session_id=session.id,
            segment_start=60,
            segment_end=70,
            text_content="点击红色按钮领取选址评估表，可以帮你避坑。",
            asr_status="completed",
        )
    )
    comments = [
        Comment(
            session_id=session.id,
            user_nickname="用户甲",
            user_sec_uid="user-a",
            comment_content="想要选址资料",
            comment_time=session.live_start_time + timedelta(seconds=120),
        ),
        Comment(
            session_id=session.id,
            user_nickname="用户乙",
            user_sec_uid="user-b",
            comment_content="预算十万可以吗",
            comment_time=session.live_start_time + timedelta(minutes=10),
        ),
    ]
    db.add_all(comments)
    _add_confirmed_lead_pair(db, session, "lead-user", 4, 40)
    db.commit()

    result = build_session_conversion_analysis(db, session, comments)
    hook = result["hook_events"][0]

    assert hook["strength"] == "strong"
    assert hook["comment_after_5m"] == 1
    assert hook["comment_after_15m"] == 2
    assert hook["lead_after_5m"] == 1


def test_events_during_hook_are_not_counted_as_after_hook(db):
    session = _session(db)
    db.add(
        TranscriptSegment(
            session_id=session.id,
            segment_start=60,
            segment_end=180,
            text_content="去后台私信领取资料，我给你发品牌名单。",
            asr_status="completed",
        )
    )
    during = Comment(
        session_id=session.id,
        user_nickname="进行中评论",
        comment_content="想要资料",
        comment_time=session.live_start_time + timedelta(seconds=120),
    )
    after = Comment(
        session_id=session.id,
        user_nickname="结束后评论",
        comment_content="怎么领取",
        comment_time=session.live_start_time + timedelta(seconds=200),
    )
    db.add_all([during, after])
    db.commit()

    result = build_session_conversion_analysis(db, session, [during, after])

    assert result["hook_events"][0]["comment_after_5m"] == 1


def test_analysis_coverage_reports_truncated_sample_truthfully(db):
    session = _session(db)

    result = build_session_conversion_analysis(db, session, [], total_comment_count=2500)

    assert result["data_coverage"]["comment_count"] == 2500
    assert result["data_coverage"]["analysis_comment_count"] == 0
    assert result["data_coverage"]["analysis_truncated"] is True
