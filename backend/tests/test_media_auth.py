"""原生头像、回放和下载的短时媒体鉴权测试。"""

from unittest.mock import patch

from app.core.security import MEDIA_ACCESS_COOKIE, create_media_access_token, create_refresh_token
from app.models.live_sessions import LiveSession


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


def test_refresh_token_cannot_be_used_as_access_token(client, test_user):
    """刷新 Token 只负责换取新 Token，不能直接访问业务接口。"""
    user, _password = test_user
    refresh_token = create_refresh_token({"sub": str(user.id)})

    response = client.get(
        "/api/v1/dashboard/summary",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )

    assert response.status_code == 401
