"""用户留资与钩子转化分析测试。"""

from datetime import datetime, timedelta

from app.models.comments import Comment
from app.models.leads import Lead
from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.models.transcript_segments import TranscriptSegment
from app.services.analysis.session_conversion import build_session_conversion_analysis


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
    db.add(
        Lead(
            session_id=session.id,
            douyin_id="@shop_123 ",
            anchor_name="测试主播",
            external_source="test",
            external_id=1,
            attribution_status="matched",
            create_time=session.live_start_time + timedelta(minutes=15),
        )
    )
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
    assert result["hook_events"][0]["hook_types"] == ["资料钩子", "私信引导", "行动指令"]


def test_analysis_coverage_reports_truncated_sample_truthfully(db):
    session = _session(db)

    result = build_session_conversion_analysis(db, session, [], total_comment_count=2500)

    assert result["data_coverage"]["comment_count"] == 2500
    assert result["data_coverage"]["analysis_comment_count"] == 0
    assert result["data_coverage"]["analysis_truncated"] is True
