"""
P0-04：复盘 API 响应契约测试

验证后端真实返回值能通过 Pydantic Schema 校验，
防止 Schema 与 Service 返回结构不一致导致页面空白。
"""
import pytest
from app.schemas.review import (
    ComplianceRuleOut,
    ReviewFindingOut,
    ReviewWorkbenchResponse,
)
from app.models.review import ComplianceRule, ReviewFinding
from app.models.live_sessions import LiveSession


def _seed_session(db):
    """插入一条最小直播场次记录，返回 session_id。"""
    session = LiveSession(
        id=1,
        room_id="713603103491",
        anchor_name="测试主播",
        douyin_id="test_anchor_001",
    )
    db.add(session)
    db.commit()
    return session.id


def _seed_finding(db, session_id: int, **overrides):
    """插入一条测试复盘发现。"""
    # SQLite 内存库不支持 BigInteger autoincrement，显式计算 ID
    from app.models.review import ReviewFinding as RF
    max_id = db.query(RF.id).order_by(RF.id.desc()).first()
    next_id = (max_id[0] + 1) if max_id and max_id[0] else 1
    finding = ReviewFinding(
        id=next_id,
        session_id=session_id,
        evidence_key=overrides.get("evidence_key", f"test-evidence-{session_id}-{next_id}"),
        finding_type=overrides.get("finding_type", "observation"),
        category=overrides.get("category", "留人"),
        title=overrides.get("title", "开播前5分钟留人率偏低"),
        description=overrides.get("description", "真实直播开场互动不足"),
        severity=overrides.get("severity", "warning"),
        evidence_type=overrides.get("evidence_type", "metric"),
        evidence_text=overrides.get("evidence_text", "开场5分钟在线人数下降30%"),
        metric_name=overrides.get("metric_name", "online_count"),
        metric_before=overrides.get("metric_before", 120.0),
        metric_after=overrides.get("metric_after", 84.0),
        source=overrides.get("source", "rule"),
        status=overrides.get("status", "open"),
    )
    db.add(finding)
    db.commit()
    db.refresh(finding)
    return finding


def _seed_compliance_rule(db, **overrides):
    """插入一条测试合规规则。"""
    # SQLite 内存库不支持 autoincrement，显式计算 ID
    max_id = db.query(ComplianceRule.id).order_by(ComplianceRule.id.desc()).first()
    next_id = (max_id[0] + 1) if max_id and max_id[0] else 1
    rule = ComplianceRule(
        id=next_id,
        rule_code=overrides.get("rule_code", "TEST_RULE_001"),
        name=overrides.get("name", "禁止绝对化用语"),
        category=overrides.get("category", "绝对化"),
        pattern=overrides.get("pattern", "最好|第一|唯一"),
        severity=overrides.get("severity", "warning"),
        guidance=overrides.get("guidance", "建议修改为相对化表述"),
        source_url=overrides.get("source_url", "https://example.com/rule"),
        version=overrides.get("version", 1),
        enabled=overrides.get("enabled", 1),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


class TestReviewWorkbenchContract:
    """GET /reviews/{session_id}/workbench 响应契约测试"""

    def test_workbench_response_validates_against_schema(self, client, auth_headers, db):
        """调用真实 workbench 接口，返回值能被 ReviewWorkbenchResponse 校验"""
        _seed_session(db)

        resp = client.get(
            "/api/v1/reviews/1/workbench",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"workbench 请求失败: {resp.json()}"

        # Pydantic 校验：如果 Schema 与真实返回值不一致，这里会抛 ValidationError
        data = resp.json()
        validated = ReviewWorkbenchResponse.model_validate(data)
        assert validated.session_id == 1

    def test_workbench_without_auth_returns_401(self, client, db):
        """未登录请求 workbench 应返回 401 / 403"""
        _seed_session(db)
        resp = client.get("/api/v1/reviews/1/workbench")
        assert resp.status_code in (401, 403), f"期望 401/403，实际 {resp.status_code}"

    def test_workbench_unknown_session_returns_404(self, client, auth_headers):
        """不存在的场次应返回 404"""
        resp = client.get("/api/v1/reviews/99999/workbench", headers=auth_headers)
        assert resp.status_code == 404


class TestUpdateFindingContract:
    """PATCH /reviews/{session_id}/findings/{finding_id} 响应契约测试"""

    def test_update_finding_returns_all_evidence_fields(self, client, auth_headers, db):
        """
        P0-02 修复验证：更新 finding 状态后，响应必须包含完整的证据字段。

        关键字段（修复前被 ReviewFindingOut 过滤掉）：
        - finding_type, description, severity
        - evidence_type, evidence_text
        - metric_name, metric_before, metric_after
        - source
        """
        session_id = _seed_session(db)
        finding = _seed_finding(db, session_id)

        resp = client.patch(
            f"/api/v1/reviews/{session_id}/findings/{finding.id}",
            json={"status": "confirmed"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"更新 finding 失败: {resp.json()}"

        data = resp.json()
        # Pydantic 校验
        validated = ReviewFindingOut.model_validate(data)

        # 验证关键字段存在且不为 None（修复前这些字段会被过滤掉）
        assert validated.finding_type is not None, "finding_type 缺失"
        assert validated.description is not None, "description 缺失"
        assert validated.severity is not None, "severity 缺失"
        assert validated.evidence_type is not None, "evidence_type 缺失"
        assert validated.evidence_text is not None, "evidence_text 缺失"
        assert validated.metric_name is not None, "metric_name 缺失"
        assert validated.metric_before is not None, "metric_before 缺失"
        assert validated.metric_after is not None, "metric_after 缺失"
        assert validated.source is not None, "source 缺失"
        # 确认状态已更新
        assert validated.status == "confirmed"


class TestComplianceRulesContract:
    """GET /reviews/compliance/rules 响应契约测试"""

    def test_rules_response_validates_against_schema(self, client, auth_headers, db):
        """调用真实 compliance/rules 接口，返回值能被 ComplianceRuleOut 校验"""
        _seed_compliance_rule(db)

        resp = client.get(
            "/api/v1/reviews/compliance/rules",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"compliance/rules 请求失败: {resp.json()}"

        data = resp.json()
        assert isinstance(data, list), "应返回列表"
        assert len(data) >= 1

        # Pydantic 校验每一条合规规则
        for item in data:
            validated = ComplianceRuleOut.model_validate(item)
            # P0-03 修复验证：模型字段 name/guidance/pattern（非 title/description）
            assert validated.name is not None, "name 缺失（旧字段 title 已废弃）"
            assert validated.guidance is not None, "guidance 缺失（旧字段 description 已废弃）"
            assert validated.rule_code is not None, "rule_code 缺失"

    def test_rules_without_auth_returns_401(self, client):
        """未登录请求 compliance/rules 应返回 401 / 403"""
        resp = client.get("/api/v1/reviews/compliance/rules")
        assert resp.status_code in (401, 403), f"期望 401/403，实际 {resp.status_code}"


class TestReviewEndpointsRequireAuth:
    """验证所有复盘端点都需要登录鉴权"""

    @pytest.mark.parametrize("method, url, body", [
        ("GET", "/api/v1/reviews/1/workbench", None),
        ("POST", "/api/v1/reviews/1/generate", None),
        ("GET", "/api/v1/reviews/1/comparison", None),
        ("PATCH", "/api/v1/reviews/1/findings/1", {"status": "confirmed"}),
        ("POST", "/api/v1/reviews/1/actions", {"title": "测试行动"}),
        ("GET", "/api/v1/reviews/compliance/rules", None),
    ])
    def test_endpoint_requires_auth(self, client, method, url, body):
        """未登录访问复盘端点应返回 401"""
        if body is not None:
            resp = getattr(client, method.lower())(url, json=body)
        else:
            resp = getattr(client, method.lower())(url)
        assert resp.status_code in (401, 403), (
            f"{method} {url} 未登录时应返回 401/403，实际 {resp.status_code}"
        )
