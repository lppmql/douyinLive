"""
M8 核心链路集成测试 — 经营仪表盘 (dashboard)
=============================================
测试链条：汇总数据 → 日期筛选 → 按主播分组
覆盖端点：GET /dashboard/summary、GET /dashboard/summary/by-anchor、GET /dashboard/operations

⚠️  P0-01 后所有业务 API 要求登录鉴权，所有测试均需带 auth_headers
"""

from datetime import datetime

import pytest


class TestDashboardSummary:
    """GET /api/v1/dashboard/summary — 核心经营指标汇总"""

    def test_summary_with_empty_db_returns_zeros(self, client, auth_headers):
        """空数据库 → 200 + 全零指标"""
        resp = client.get("/api/v1/dashboard/summary", headers=auth_headers)

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

    def test_summary_with_sessions(self, client, db, auth_headers):
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

        resp = client.get("/api/v1/dashboard/summary", headers=auth_headers)

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

    def test_summary_with_date_filter(self, client, db, auth_headers):
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
            headers=auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["session_count"] == 1
        assert data["total_viewers"] == 1000
        assert data["total_leads"] == 5

    def test_summary_with_date_filter_no_results(self, client, auth_headers):
        """日期范围内无数据 → 全零"""
        resp = client.get(
            "/api/v1/dashboard/summary",
            params={"start_date": "2025-01-01", "end_date": "2025-01-01"},
            headers=auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["session_count"] == 0


class TestDashboardByAnchor:
    """GET /api/v1/dashboard/summary/by-anchor — 按主播分组汇总"""

    def test_by_anchor_empty_db_returns_empty(self, client, auth_headers):
        """空数据库 → 空列表 + 全零汇总"""
        resp = client.get("/api/v1/dashboard/summary/by-anchor", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["anchors"] == []
        assert data["total"]["session_count"] == 0

    def test_by_anchor_groups_correctly(self, client, db, auth_headers):
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

        resp = client.get("/api/v1/dashboard/summary/by-anchor", headers=auth_headers)

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

    def test_by_anchor_with_date_filter(self, client, db, auth_headers):
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
            headers=auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["anchors"]) == 1
        assert data["anchors"][0]["session_count"] == 1
        assert data["anchors"][0]["total_viewers"] == 2000
        assert data["total"]["session_count"] == 1

    def test_by_anchor_uses_live_time_instead_of_backfill_id_for_latest_snapshot(self, client, db, auth_headers):
        """历史回填的高 ID 不能覆盖时间上更新的主播身份快照。"""
        from app.models.live_rooms import LiveRoom
        from app.models.live_sessions import LiveSession

        room = LiveRoom(account_name="回填测试账号", anchor_name="主播新名称")
        db.add(room)
        db.flush()
        newest = LiveSession(
            room_id=room.id,
            douyin_id="stable_anchor",
            anchor_name="主播新名称",
            anchor_avatar_url="https://example.invalid/new-avatar.png",
            live_start_time=datetime(2026, 8, 29, 10, 0, 0),
        )
        db.add(newest)
        db.flush()
        historical_backfill = LiveSession(
            room_id=room.id,
            douyin_id="stable_anchor",
            anchor_name="主播旧名称",
            anchor_avatar_url="https://example.invalid/old-avatar.png",
            live_start_time=datetime(2026, 7, 1, 10, 0, 0),
        )
        db.add(historical_backfill)
        db.commit()

        resp = client.get("/api/v1/dashboard/summary/by-anchor", headers=auth_headers)

        assert resp.status_code == 200
        item = resp.json()["anchors"][0]
        assert historical_backfill.id > newest.id
        assert item["anchor_name"] == "主播新名称"
        assert item["anchor_avatar_url"] == "https://example.invalid/new-avatar.png"
        assert item["anchor_avatar_session_id"] == newest.id


class TestDashboardOperations:
    """GET /api/v1/dashboard/operations — 原生经营大屏组合数据。"""

    def test_operations_returns_filtered_real_business_metrics(self, client, db, auth_headers):
        """组合接口应复用公共主播键，并返回趋势、漏斗和场次明细。"""
        from app.models.live_rooms import LiveRoom
        from app.models.live_sessions import LiveSession

        room = LiveRoom(account_name="原生大屏测试账号", anchor_name="主播A")
        db.add(room)
        db.flush()
        db.add_all([
            LiveSession(
                room_id=room.id,
                douyin_id="douyin_a",
                anchor_name="主播A",
                session_title="主播A真实场次",
                live_start_time=datetime(2026, 8, 28, 10, 0, 0),
                live_exposure_users=1000,
                live_enter_users=400,
                card_click_users=80,
                private_message_count=20,
                leads_count=10,
                total_viewers=500,
                comments_count=60,
                ad_cost=200,
            ),
            LiveSession(
                room_id=room.id,
                douyin_id="douyin_b",
                anchor_name="主播B",
                session_title="主播B真实场次",
                live_start_time=datetime(2026, 8, 28, 14, 0, 0),
                live_exposure_users=2000,
                live_enter_users=800,
                card_click_users=160,
                private_message_count=40,
                leads_count=20,
                total_viewers=1000,
                comments_count=120,
                ad_cost=500,
            ),
        ])
        db.commit()

        resp = client.get(
            "/api/v1/dashboard/operations",
            params={
                "start_date": "2026-08-28",
                "end_date": "2026-08-28",
                "anchor_key": "dyid:douyin_a",
            },
            headers=auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["session_count"] == 1
        assert data["summary"]["total_leads"] == 10
        assert data["summary"]["average_lead_cost"] == 20.0
        assert [item["anchor_key"] for item in data["anchors"]] == ["dyid:douyin_a"]
        assert data["trend"] == [{
            "date_key": "2026-08-28",
            "session_count": 1,
            "total_viewers": 500,
            "total_comments": 60,
            "total_private_messages": 20,
            "total_leads": 10,
            "total_ad_cost": 200.0,
        }]
        assert [item["value"] for item in data["funnel"]] == [1000, 400, 80, 20, 10]
        assert [item["step_rate"] for item in data["funnel"]] == [100.0, 40.0, 20.0, 25.0, 50.0]
        assert len(data["recent_sessions"]) == 1
        assert data["recent_sessions"][0]["session_title"] == "主播A真实场次"


@pytest.mark.parametrize(
    "path",
    (
        "/api/v1/dashboard/summary",
        "/api/v1/dashboard/summary/by-anchor",
        "/api/v1/dashboard/operations",
    ),
)
def test_dashboard_routes_reject_reversed_date_range(path, client, auth_headers):
    """三个大屏接口必须和公共场次选择器一样把反向日期返回为 422。"""
    resp = client.get(
        path,
        params={"start_date": "2026-08-30", "end_date": "2026-08-01"},
        headers=auth_headers,
    )

    assert resp.status_code == 422
