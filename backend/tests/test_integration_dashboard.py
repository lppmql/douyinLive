"""
M8 核心链路集成测试 — 经营仪表盘 (dashboard)
=============================================
测试链条：汇总数据 → 日期筛选 → 按主播分组
覆盖端点：GET /dashboard/summary, GET /dashboard/summary/by-anchor
"""

from datetime import datetime


class TestDashboardSummary:
    """GET /api/v1/dashboard/summary — 核心经营指标汇总"""

    def test_summary_with_empty_db_returns_zeros(self, client):
        """空数据库 → 200 + 全零指标"""
        resp = client.get("/api/v1/dashboard/summary")

        assert resp.status_code == 200
        data = resp.json()
        assert data["session_count"] == 0
        assert data["anchor_count"] == 0
        assert data["total_viewers"] == 0
        assert data["total_comments"] == 0
        assert data["total_private_messages"] == 0
        assert data["total_leads"] == 0
        assert data["total_ad_cost"] == 0.0
        assert data["average_lead_cost"] == 0.0
        assert data["detail_completion_rate"] == 0.0
        assert data["open_review_action_count"] == 0

    def test_summary_with_sessions(self, client, db):
        """有直播场次数据 → 返回正确的汇总值"""
        from app.models.live_rooms import LiveRoom
        from app.models.live_sessions import LiveSession

        # 创建直播间（LiveSession 依赖的外键）
        room = LiveRoom(account_name="测试账号", anchor_name="主播A")
        db.add(room)
        db.flush()

        # 创建 3 个场次
        sessions = [
            LiveSession(
                room_id=room.id,
                douyin_id="douyin_a",
                anchor_name="主播A",
                live_start_time=datetime(2026, 7, 20, 10, 0, 0),
                total_viewers=1000,
                comments_count=50,
                private_message_count=10,
                leads_count=5,
                ad_cost=100.0,
                live_status="finished",
            ),
            LiveSession(
                room_id=room.id,
                douyin_id="douyin_a",
                anchor_name="主播A",
                live_start_time=datetime(2026, 7, 20, 14, 0, 0),
                total_viewers=2000,
                comments_count=80,
                private_message_count=15,
                leads_count=8,
                ad_cost=200.0,
                live_status="finished",
            ),
            LiveSession(
                room_id=room.id,
                douyin_id="douyin_b",
                anchor_name="主播B",
                live_start_time=datetime(2026, 7, 21, 9, 0, 0),
                total_viewers=3000,
                comments_count=120,
                private_message_count=20,
                leads_count=12,
                ad_cost=300.0,
                live_status="live",
            ),
        ]
        db.add_all(sessions)
        db.commit()

        resp = client.get("/api/v1/dashboard/summary")

        assert resp.status_code == 200
        data = resp.json()
        assert data["session_count"] == 3
        assert data["anchor_count"] == 2  # douyin_a + douyin_b
        assert data["live_session_count"] == 1  # 只有第3场 live_status="live"
        assert data["total_viewers"] == 6000  # 1000+2000+3000
        assert data["total_comments"] == 250  # 50+80+120
        assert data["total_private_messages"] == 45  # 10+15+20
        assert data["total_leads"] == 25  # 5+8+12
        assert data["total_ad_cost"] == 600.0  # 100+200+300

    def test_summary_with_date_filter(self, client, db):
        """日期筛选：只统计指定日期范围内的场次"""
        from app.models.live_rooms import LiveRoom
        from app.models.live_sessions import LiveSession

        room = LiveRoom(account_name="测试账号", anchor_name="主播A")
        db.add(room)
        db.flush()

        # 7月20日的场次
        db.add(
            LiveSession(
                room_id=room.id,
                douyin_id="douyin_a",
                anchor_name="主播A",
                live_start_time=datetime(2026, 7, 20, 10, 0, 0),
                total_viewers=1000,
                leads_count=5,
            )
        )
        # 7月21日的场次
        db.add(
            LiveSession(
                room_id=room.id,
                douyin_id="douyin_a",
                anchor_name="主播A",
                live_start_time=datetime(2026, 7, 21, 14, 0, 0),
                total_viewers=2000,
                leads_count=10,
            )
        )
        db.commit()

        # 只查7月20日
        resp = client.get(
            "/api/v1/dashboard/summary",
            params={"start_date": "2026-07-20", "end_date": "2026-07-20"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["session_count"] == 1
        assert data["total_viewers"] == 1000
        assert data["total_leads"] == 5

    def test_summary_with_date_filter_no_results(self, client, db):
        """日期范围内无数据 → 全零"""
        resp = client.get(
            "/api/v1/dashboard/summary",
            params={"start_date": "2025-01-01", "end_date": "2025-01-01"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["session_count"] == 0


class TestDashboardByAnchor:
    """GET /api/v1/dashboard/summary/by-anchor — 按主播分组汇总"""

    def test_by_anchor_empty_db_returns_empty(self, client):
        """空数据库 → 空列表 + 全零汇总"""
        resp = client.get("/api/v1/dashboard/summary/by-anchor")

        assert resp.status_code == 200
        data = resp.json()
        assert data["anchors"] == []
        assert data["total"]["session_count"] == 0

    def test_by_anchor_groups_correctly(self, client, db):
        """按主播分组，每个主播一行"""
        from app.models.live_rooms import LiveRoom
        from app.models.live_sessions import LiveSession

        room = LiveRoom(account_name="测试账号", anchor_name="主播A")
        db.add(room)
        db.flush()

        # 主播A: 2场
        db.add_all([
            LiveSession(
                room_id=room.id,
                douyin_id="douyin_a",
                anchor_name="主播A",
                live_start_time=datetime(2026, 7, 20, 10, 0, 0),
                total_viewers=1000,
                comments_count=50,
                private_message_count=10,
                leads_count=5,
                ad_cost=100.0,
            ),
            LiveSession(
                room_id=room.id,
                douyin_id="douyin_a",
                anchor_name="主播A",
                live_start_time=datetime(2026, 7, 20, 14, 0, 0),
                total_viewers=2000,
                comments_count=80,
                private_message_count=15,
                leads_count=8,
                ad_cost=200.0,
            ),
        ])
        db.commit()

        resp = client.get("/api/v1/dashboard/summary/by-anchor")

        assert resp.status_code == 200
        data = resp.json()
        anchors = data["anchors"]
        assert len(anchors) == 1
        assert anchors[0]["douyin_id"] == "douyin_a"
        assert anchors[0]["anchor_name"] == "主播A"
        assert anchors[0]["session_count"] == 2
        assert anchors[0]["total_viewers"] == 3000
        assert anchors[0]["total_leads"] == 13
        assert anchors[0]["total_ad_cost"] == 300.0

        # 汇总行
        total = data["total"]
        assert total["session_count"] == 2
        assert total["total_viewers"] == 3000

    def test_by_anchor_with_date_filter(self, client, db):
        """按主播分组 + 日期筛选"""
        from app.models.live_rooms import LiveRoom
        from app.models.live_sessions import LiveSession

        room = LiveRoom(account_name="测试账号", anchor_name="主播A")
        db.add(room)
        db.flush()

        db.add_all([
            LiveSession(
                room_id=room.id,
                douyin_id="douyin_a",
                anchor_name="主播A",
                live_start_time=datetime(2026, 7, 20, 10, 0, 0),
                total_viewers=1000,
                leads_count=5,
            ),
            LiveSession(
                room_id=room.id,
                douyin_id="douyin_a",
                anchor_name="主播A",
                live_start_time=datetime(2026, 7, 21, 14, 0, 0),
                total_viewers=2000,
                leads_count=10,
            ),
        ])
        db.commit()

        # 只查7月21日
        resp = client.get(
            "/api/v1/dashboard/summary/by-anchor",
            params={"start_date": "2026-07-21", "end_date": "2026-07-21"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["anchors"]) == 1
        assert data["anchors"][0]["session_count"] == 1
        assert data["anchors"][0]["total_viewers"] == 2000
        assert data["total"]["session_count"] == 1
