"""原生头像、回放和下载的短时媒体鉴权测试。"""

from unittest.mock import patch

import pytest
from starlette.websockets import WebSocketDisconnect

from app.core.security import (
    MEDIA_ACCESS_COOKIE,
    _MEDIA_PATH_PATTERN,
    build_internal_worker_token,
    create_media_access_token,
    create_refresh_token,
    create_access_token,
)
from app.models.live_sessions import LiveSession
from app.models.user import User


def test_login_sets_httponly_media_cookie(client, test_user):
    """登录后浏览器应收到 HttpOnly Cookie，主登录 Token 不进入媒体 URL。"""
    user, password = test_user
    response = client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": password},
    )

    assert response.status_code == 200
    cookie = response.headers.get("set-cookie", "")
    assert MEDIA_ACCESS_COOKIE in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie


def test_media_cookie_can_read_avatar_without_bearer(client, db, test_user):
    """原生 img 标签没有 Authorization 头，也应能读取已鉴权的真实头像代理。"""
    user, _password = test_user
    session = LiveSession(
        room_id=1,
        anchor_name="真实主播",
        anchor_avatar_url="https://p3.douyinpic.com/avatar.webp",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    client.cookies.set(MEDIA_ACCESS_COOKIE, create_media_access_token(user.id))

    with patch("app.api.v1.live_sessions.httpx.get") as mocked_get:
        mocked_get.return_value.status_code = 200
        mocked_get.return_value.content = b"real-image"
        mocked_get.return_value.headers = {"content-type": "image/webp"}
        response = client.get(f"/api/v1/live-sessions/{session.id}/avatar")

    assert response.status_code == 200
    assert response.content == b"real-image"


def test_media_cookie_cannot_access_business_api(client, test_user):
    """媒体 Cookie 只能读媒体文件，不能替代 Bearer Token 调用业务接口。"""
    user, _password = test_user
    client.cookies.set(MEDIA_ACCESS_COOKIE, create_media_access_token(user.id))

    response = client.get("/api/v1/dashboard/summary")

    assert response.status_code == 401


def test_clip_subtitle_download_is_scoped_as_media_path():
    """ASS/SRT 下载可使用短时媒体 Cookie，但字幕重制业务接口不能。"""
    assert _MEDIA_PATH_PATTERN.fullmatch("/api/v1/clip/clips/12/subtitle")
    assert _MEDIA_PATH_PATTERN.fullmatch("/api/v1/clip/clips/12/subtitle.srt")
    assert not _MEDIA_PATH_PATTERN.fullmatch("/api/v1/clip/clips/12/subtitle/rerender")


def test_refresh_token_cannot_be_used_as_access_token(client, test_user):
    """刷新 Token 只负责换取新 Token，不能直接访问业务接口。"""
    user, _password = test_user
    refresh_token = create_refresh_token({"sub": str(user.id)})

    response = client.get(
        "/api/v1/dashboard/summary",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )

    assert response.status_code == 401


def test_stream_and_refresh_require_authentication(client):
    """媒体流和刷新接口不再允许匿名调用。"""
    assert client.get("/api/v1/live-sessions/1/stream").status_code == 401
    assert client.get("/api/v1/live-sessions/1/playback").status_code == 401
    assert client.post("/api/v1/live-sessions/1/refresh-stream").status_code == 401


def test_internal_worker_token_can_refresh_stream(client):
    """ASR Worker 使用内部凭证，不需要伪装成浏览器用户。"""
    with patch("app.api.v1.live_sessions.refresh_session_stream_url") as refresh:
        refresh.return_value = {
            "success": True,
            "error": None,
            "stream_url": "https://example.invalid/real-stream.m3u8",
            "source": "saved-browser-session",
        }
        response = client.post(
            "/api/v1/live-sessions/1/refresh-stream",
            headers={"X-Internal-Worker-Token": build_internal_worker_token()},
        )

    assert response.status_code == 200
    assert response.json()["source"] == "saved-browser-session"


def test_viewer_cannot_refresh_stream(client, db):
    """刷新流地址会写数据库，只读账号即使已登录也不能触发。"""
    viewer = User(
        username="stream-viewer",
        password_hash="not-used",
        nickname="只读账号",
        roles=["R_VIEWER"],
        status="active",
    )
    db.add(viewer)
    db.commit()
    db.refresh(viewer)

    response = client.post(
        "/api/v1/live-sessions/1/refresh-stream",
        headers={
            "Authorization": f"Bearer {create_access_token({'sub': str(viewer.id)})}"
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "当前账号没有执行此操作的权限"


def test_transcript_websocket_rejects_anonymous_connection(client):
    """未登录浏览器不能订阅直播中的真实话术。"""
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/transcript/1"):
            pass

    assert exc_info.value.code == 4401
