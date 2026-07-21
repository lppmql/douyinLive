"""
M8 核心链路集成测试 — 认证 (auth)
=================================
测试链条：登录 → 获取用户信息 → 刷新 Token
覆盖 3 个端点：POST /auth/login, GET /auth/getUserInfo, POST /auth/refreshToken
"""

class TestAuthLogin:
    """POST /api/v1/auth/login — 用户登录"""

    def test_login_success_returns_tokens(self, client, test_user):
        """正确用户名+密码 → 200 + access token + refresh token"""
        user, password = test_user
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": user.username, "password": password},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == "0000"
        assert "token" in body["data"]
        assert "refreshToken" in body["data"]
        assert len(body["data"]["token"]) > 0
        assert len(body["data"]["refreshToken"]) > 0

    def test_login_wrong_password_returns_401(self, client, test_user):
        """错误密码 → 401"""
        user, _password = test_user
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": user.username, "password": "wrong_password"},
        )

        assert resp.status_code == 401

    def test_login_nonexistent_user_returns_401(self, client):
        """不存在的用户 → 401"""
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "nobody", "password": "anything"},
        )

        assert resp.status_code == 401

    def test_login_disabled_user_returns_403(self, client, db):
        """被禁用的用户 → 403"""
        from app.models.user import User
        from app.core.security import get_password_hash

        disabled = User(
            username="disabled_user",
            password_hash=get_password_hash("test123456"),
            status="disabled",
        )
        db.add(disabled)
        db.commit()

        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "disabled_user", "password": "test123456"},
        )

        assert resp.status_code == 403


class TestGetUserInfo:
    """GET /api/v1/auth/getUserInfo — 获取当前用户信息"""

    def test_returns_user_info_with_valid_token(self, client, auth_headers):
        """有效 token → 200 + 用户信息"""
        resp = client.get("/api/v1/auth/getUserInfo", headers=auth_headers)

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == "0000"
        data = body["data"]
        assert data["userName"] == "testuser"
        assert "R_ADMIN" in data["roles"]
        assert data["userId"] != ""

    def test_returns_401_without_token(self, client):
        """无 token → 401（HTTPBearer 拒绝）"""
        resp = client.get("/api/v1/auth/getUserInfo")
        # HTTPBearer 在没有 Authorization header 时返回 403
        assert resp.status_code in (401, 403)

    def test_returns_401_with_invalid_token(self, client):
        """伪造 token → 401"""
        resp = client.get(
            "/api/v1/auth/getUserInfo",
            headers={"Authorization": "Bearer invalid_token_here"},
        )
        assert resp.status_code == 401


class TestRefreshToken:
    """POST /api/v1/auth/refreshToken — 刷新 Token"""

    def test_refresh_returns_new_tokens(self, client, test_user):
        """用合法 refreshToken 换取新 token 对"""
        user, password = test_user
        # 先登录获取 refreshToken
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"username": user.username, "password": password},
        )
        refresh_token = login_resp.json()["data"]["refreshToken"]

        # 用 refreshToken 刷新
        resp = client.post(
            "/api/v1/auth/refreshToken",
            json={"refreshToken": refresh_token},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == "0000"
        assert "token" in body["data"]
        assert "refreshToken" in body["data"]

    def test_refresh_with_invalid_token_returns_401(self, client):
        """伪造 refreshToken → 401"""
        resp = client.post(
            "/api/v1/auth/refreshToken",
            json={"refreshToken": "garbage_token"},
        )
        assert resp.status_code == 401
