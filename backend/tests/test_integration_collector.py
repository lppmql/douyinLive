"""
M8 核心链路集成测试 — 数据采集 (collector)
==========================================
测试链条：采集器状态 → 账号 CRUD → 采集日志
覆盖端点：GET /collector/status, /accounts CRUD, /logs
注意：collect-all、login-qr、re-login 等需要浏览器/Redis 的端点不在此测试

⚠️  P0-01 后所有业务 API 要求登录鉴权，所有测试均需带 auth_headers
"""


class TestCollectorStatus:
    """GET /api/v1/collector/status — 采集器状态"""

    def test_status_returns_ok_with_empty_db(self, client, auth_headers):
        """空数据库 → 200，connected=false, active_task_count=0"""
        resp = client.get("/api/v1/collector/status", headers=auth_headers)

        assert resp.status_code == 200
        body = resp.json()
        # collector/status 返回外层无 SoybeanResponse 包装（直接 CollectorStatusResponse）
        assert body.get("connected") is False
        assert body.get("active_task_count") == 0
        assert body.get("default_account") is None

    def test_status_returns_connected_with_account(self, client, db, auth_headers):
        """有账号 → connected=true"""
        from app.models.scraper_accounts import ScraperAccount

        account = ScraperAccount(
            account_name="测试账号",
            douyin_id="test_douyin_id",
            login_status="logged_in",
        )
        db.add(account)
        db.commit()

        resp = client.get("/api/v1/collector/status", headers=auth_headers)

        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is True
        assert body["default_account"]["account_name"] == "测试账号"


class TestCollectorAccounts:
    """采集账号 CRUD — GET/POST/PUT/DELETE /api/v1/collector/accounts"""

    def test_list_accounts_empty(self, client, auth_headers):
        """空列表 → 200 + []"""
        resp = client.get("/api/v1/collector/accounts", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_and_list_account(self, client, auth_headers):
        """创建账号后列表可见"""
        # 创建
        create_resp = client.post(
            "/api/v1/collector/accounts",
            json={"account_name": "新账号", "douyin_id": "douyin_001"},
            headers=auth_headers,
        )
        assert create_resp.status_code == 200
        created = create_resp.json()
        assert created["account_name"] == "新账号"
        assert created["douyin_id"] == "douyin_001"
        assert created["login_status"] == "never"
        assert "id" in created

        # 列表
        list_resp = client.get("/api/v1/collector/accounts", headers=auth_headers)
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 1
        assert list_resp.json()[0]["account_name"] == "新账号"

    def test_get_single_account(self, client, db, auth_headers):
        """获取单个账号详情"""
        from app.models.scraper_accounts import ScraperAccount

        account = ScraperAccount(account_name="详情账号", douyin_id="detail_001")
        db.add(account)
        db.commit()
        db.refresh(account)

        resp = client.get(f"/api/v1/collector/accounts/{account.id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["account_name"] == "详情账号"

    def test_get_nonexistent_account_returns_404(self, client, auth_headers):
        """不存在的账号 → 404"""
        resp = client.get("/api/v1/collector/accounts/99999", headers=auth_headers)
        assert resp.status_code == 404

    def test_update_account(self, client, db, auth_headers):
        """更新账号字段"""
        from app.models.scraper_accounts import ScraperAccount

        account = ScraperAccount(account_name="旧名称", douyin_id="old_id")
        db.add(account)
        db.commit()
        db.refresh(account)

        resp = client.put(
            f"/api/v1/collector/accounts/{account.id}",
            json={"account_name": "新名称", "douyin_id": "new_id"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["account_name"] == "新名称"
        assert resp.json()["douyin_id"] == "new_id"

    def test_delete_account(self, client, db, auth_headers):
        """删除账号 → 200，列表中不再出现"""
        from app.models.scraper_accounts import ScraperAccount

        account = ScraperAccount(account_name="待删账号")
        db.add(account)
        db.commit()
        db.refresh(account)

        resp = client.delete(f"/api/v1/collector/accounts/{account.id}", headers=auth_headers)
        assert resp.status_code == 200

        # 验证已删除
        list_resp = client.get("/api/v1/collector/accounts", headers=auth_headers)
        assert len(list_resp.json()) == 0

    def test_create_account_with_minimal_fields(self, client, auth_headers):
        """只填必填字段创建账号"""
        resp = client.post("/api/v1/collector/accounts", json={}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["login_status"] == "never"
        assert resp.json()["account_name"] is None


class TestCollectorLogs:
    """采集日志 — GET/DELETE /api/v1/collector/logs"""

    def test_list_logs_empty(self, client, auth_headers):
        """空日志列表 → 返回空数组"""
        resp = client.get("/api/v1/collector/logs", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_clear_logs(self, client, auth_headers):
        """清空日志（空数据库也不会报错）"""
        resp = client.delete("/api/v1/collector/logs", headers=auth_headers)
        assert resp.status_code == 200


class TestCollectorTasks:
    """采集任务 — GET /api/v1/collector/tasks"""

    def test_list_tasks_empty(self, client, auth_headers):
        """空任务列表 → 返回空数组"""
        resp = client.get("/api/v1/collector/tasks", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []
