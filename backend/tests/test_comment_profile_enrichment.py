"""评论用户公开资料补全服务测试。"""

import asyncio
from datetime import datetime, timedelta
import httpx
import pytest

from app.models.comment_user_profiles import CommentUserProfile
from app.models.comments import Comment
from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.services.collector import comment_profile_enrichment as service


def test_fetch_profile_accepts_real_public_fields_and_validates_identity():
    """成功响应必须保留两类公开抖音号，并优先选择自定义号。"""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "status_code": 0,
                "user_info": {
                    "sec_uid": "stable-user",
                    "nickname": "公开昵称",
                    "unique_id": "public_name",
                    "short_id": "123456",
                    "avatar_thumb": {
                        "url_list": ["https://p3.douyinpic.com/avatar.jpeg"]
                    },
                },
            },
        )
    )

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            return await service._fetch_profile(client, "stable-user")

    profile = asyncio.run(run())

    assert profile["public_douyin_id"] == "public_name"
    assert profile["douyin_id_type"] == "unique_id"
    assert profile["short_id"] == "123456"
    assert profile["avatar_url"] == "https://p3.douyinpic.com/avatar.jpeg"


def test_fetch_profile_rejects_mismatched_sec_uid():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"status_code": 0, "user_info": {"sec_uid": "another-user"}},
        )
    )

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            return await service._fetch_profile(client, "stable-user")

    with pytest.raises(RuntimeError, match="PROFILE_IDENTITY_MISMATCH"):
        asyncio.run(run())


def test_save_success_updates_global_cache_and_all_comment_copies(db, monkeypatch):
    room = LiveRoom(
        account_name="账号", anchor_name="主播", room_id_str="profile-cache-room"
    )
    db.add(room)
    db.flush()
    session = LiveSession(room_id=room.id, live_status="ended")
    db.add(session)
    db.flush()
    db.add_all(
        [
            Comment(
                session_id=session.id,
                user_sec_uid="stable-user",
                comment_content="第一条",
            ),
            Comment(
                session_id=session.id,
                user_sec_uid="stable-user",
                comment_content="第二条",
            ),
        ]
    )
    db.commit()
    monkeypatch.setattr(service, "SessionLocal", lambda: db)

    service._save_success(
        "stable-user",
        {
            "nickname": "公开昵称",
            "avatar_url": "https://p3.douyinpic.com/avatar.jpeg",
            "unique_id": None,
            "short_id": "123456",
            "public_douyin_id": "123456",
            "douyin_id_type": "short_id",
        },
    )

    profile = db.query(CommentUserProfile).filter_by(sec_uid="stable-user").one()
    comments = db.query(Comment).filter_by(user_sec_uid="stable-user").all()
    assert profile.fetch_status == "success"
    assert profile.public_douyin_id == "123456"
    assert all(item.user_douyin_id == "123456" for item in comments)
    assert all(item.user_avatar_url for item in comments)


def test_force_refresh_still_respects_platform_retry_after(db, monkeypatch):
    room = LiveRoom(
        account_name="账号", anchor_name="主播", room_id_str="profile-retry-room"
    )
    db.add(room)
    db.flush()
    session = LiveSession(room_id=room.id, live_status="ended")
    db.add(session)
    db.flush()
    db.add_all(
        [
            Comment(
                session_id=session.id,
                user_sec_uid="cooldown-user",
                comment_content="想要资料",
            ),
            CommentUserProfile(
                sec_uid="cooldown-user",
                fetch_status="blocked",
                retry_after=datetime.utcnow() + timedelta(hours=1),
            ),
        ]
    )
    db.commit()
    monkeypatch.setattr(service, "SessionLocal", lambda: db)

    assert service._candidate_sec_uids(session.id, force=True) == []


def test_cached_profile_is_automatically_copied_to_returning_user_comment(db, monkeypatch):
    """回访用户的新评论应复用已验证缓存，不应等待或重复请求平台。"""
    room = LiveRoom(account_name="账号", anchor_name="主播", room_id_str="returning-user-room")
    db.add(room)
    db.flush()
    session = LiveSession(room_id=room.id, live_status="live")
    db.add(session)
    db.flush()
    profile = CommentUserProfile(
        sec_uid="returning-user",
        avatar_url="https://p3.douyinpic.com/cached.jpeg",
        public_douyin_id="cached_public_id",
        fetch_status="success",
        last_fetched_at=datetime.utcnow(),
    )
    comment = Comment(
        session_id=session.id,
        user_sec_uid="returning-user",
        comment_content="再次进入直播间",
    )
    db.add_all([profile, comment])
    db.commit()
    session_id = session.id
    comment_id = comment.id
    monkeypatch.setattr(service, "SessionLocal", lambda: db)

    assert service._sync_cached_profiles_to_comments(session_id) == 1
    comment = db.get(Comment, comment_id)
    assert comment.user_avatar_url == "https://p3.douyinpic.com/cached.jpeg"
    assert comment.user_douyin_id == "cached_public_id"
    assert service._candidate_sec_uids(session_id, force=False) == []


def test_manager_rejects_different_scope_while_task_is_running():
    manager = service.CommentProfileEnrichmentManager()

    async def run():
        manager._state["scope"] = "session:1"
        manager._task = asyncio.create_task(asyncio.sleep(1))
        try:
            with pytest.raises(RuntimeError, match="PROFILE_TASK_BUSY"):
                manager.start(session_id=2)
        finally:
            manager._task.cancel()
            await asyncio.gather(manager._task, return_exceptions=True)

    asyncio.run(run())


def test_manager_sets_starting_scope_before_background_task_runs(monkeypatch):
    manager = service.CommentProfileEnrichmentManager()
    monkeypatch.setattr(
        service,
        "profile_configuration_status",
        lambda: {"configured": True, "fingerprint_configured": True},
    )

    async def idle_run(session_id, force, candidate_limit=None):
        await asyncio.sleep(1)

    monkeypatch.setattr(manager, "_run", idle_run)

    async def run():
        state = manager.start(session_id=9)
        try:
            assert state["status"] == "starting"
            assert state["scope"] == "session:9"
        finally:
            manager._task.cancel()
            await asyncio.gather(manager._task, return_exceptions=True)

    asyncio.run(run())


def test_automatic_service_starts_global_enrichment_without_manual_action(monkeypatch):
    """后台服务启动后应自动扫描全部新增用户，重复启动不能创建第二个循环。"""
    manager = service.CommentProfileEnrichmentManager()
    calls = []
    monkeypatch.setattr(
        service,
        "profile_configuration_status",
        lambda: {"configured": True, "fingerprint_configured": True},
    )

    async def record_run(session_id, force, candidate_limit=None):
        calls.append((session_id, force, candidate_limit))

    monkeypatch.setattr(manager, "_run", record_run)

    async def run():
        await manager.start_automatic()
        automatic_task = manager._automatic_task
        await manager.start_automatic()
        assert manager._automatic_task is automatic_task
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert calls == [(None, False, service.settings.DOUYIN_PROFILE_BATCH_SIZE)]
        await manager.stop_automatic()
        assert not manager.automatic_running

    asyncio.run(run())


def test_automatic_service_waits_when_profile_cookie_is_unavailable(monkeypatch):
    """专用 Cookie 缺失时后台保持待命，不能创建失败请求或影响主采集。"""
    manager = service.CommentProfileEnrichmentManager()
    monkeypatch.setattr(
        service,
        "profile_configuration_status",
        lambda: {"configured": False, "fingerprint_configured": True},
    )

    async def run():
        await manager.start_automatic()
        await asyncio.sleep(0)
        assert manager._task is None
        await manager.stop_automatic()

    asyncio.run(run())
