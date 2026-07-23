"""评论用户真实资料提取与增量补全测试。"""

from datetime import datetime, timedelta

from app.models.comments import Comment
from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.services.collector.comments import _parse_comment_user_profile, _save_comments


def test_parse_comment_user_profile_supports_nested_real_fields():
    payload = {
        "secUId": "MS4wLjABAAAA-stable-only",
        "userInfo": {
            "nickName": "真实评论用户",
            "uniqueId": "douyin_public_123",
            "avatarThumb": {"urlList": ["https://p3.douyinpic.com/avatar.jpeg"]},
        },
    }

    profile = _parse_comment_user_profile(payload)

    assert profile == {
        "user_nickname": "真实评论用户",
        "user_avatar_url": "https://p3.douyinpic.com/avatar.jpeg",
        "user_douyin_id": "douyin_public_123",
    }


def test_parse_comment_user_profile_never_uses_sec_uid_as_douyin_id():
    profile = _parse_comment_user_profile({"nickName": "只有昵称", "secUId": "stable-secret-id"})

    assert profile["user_nickname"] == "只有昵称"
    assert profile["user_douyin_id"] is None
    assert profile["user_avatar_url"] is None


def test_incremental_comment_collection_fills_missing_profile_without_duplicate(db):
    now = datetime.utcnow()
    room = LiveRoom(account_name="测试账号", anchor_name="测试主播", room_id_str="comment-profile-room")
    db.add(room)
    db.flush()
    session = LiveSession(
        room_id=room.id,
        anchor_name="测试主播",
        live_start_time=now - timedelta(minutes=10),
        live_end_time=now + timedelta(minutes=10),
        live_status="live",
    )
    db.add(session)
    db.flush()
    comment = Comment(
        id=1,
        session_id=session.id,
        user_nickname="同一用户",
        user_sec_uid="stable-user",
        comment_content="想要预算表",
        comment_time=now,
    )
    db.add(comment)
    db.commit()

    inserted = _save_comments(
        db,
        session.id,
        [
            {
                "user_nickname": "同一用户",
                "user_sec_uid": "stable-user",
                "user_avatar_url": "https://p3.douyinpic.com/real-avatar.jpeg",
                "user_douyin_id": "real_douyin_id",
                "comment_content": "想要预算表",
                "comment_time": now,
            }
        ],
    )

    db.expire_all()
    rows = db.query(Comment).filter(Comment.session_id == session.id).all()
    assert inserted == 0
    assert len(rows) == 1
    assert rows[0].user_avatar_url == "https://p3.douyinpic.com/real-avatar.jpeg"
    assert rows[0].user_douyin_id == "real_douyin_id"
