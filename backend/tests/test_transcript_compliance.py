from app.models.review import ComplianceRule
from app.models.live_sessions import LiveSession
from app.models.transcript_segments import TranscriptSegment
from app.services.transcript_compliance import (
    ComplianceRuleSnapshot,
    load_enabled_compliance_rules,
    match_compliance_text,
)


def test_compliance_keyword_match_is_traceable_and_marked_suspected():
    rules = [
        ComplianceRule(
            rule_code="ABSOLUTE_PROMISE",
            name="绝对化承诺",
            category="绝对化",
            pattern="百分百|绝对赚钱",
            severity="critical",
            guidance="删除绝对化承诺，并补充适用条件和真实依据。",
            version=1,
            enabled=1,
        )
    ]

    hits = match_compliance_text("这个项目百分百可以回本", rules)

    assert hits == [
        {
            "rule_code": "ABSOLUTE_PROMISE",
            "name": "绝对化承诺",
            "category": "绝对化",
            "matched_keyword": "百分百",
            "severity": "critical",
            "guidance": "删除绝对化承诺，并补充适用条件和真实依据。",
            "review_status": "suspected",
        }
    ]


def test_compliance_keyword_match_ignores_empty_text_and_duplicate_versions():
    older = ComplianceRule(
        rule_code="OFFSITE",
        name="站外导流",
        category="站外导流",
        pattern="加微信",
        severity="warning",
        guidance="改为站内私信。",
        version=2,
        enabled=1,
    )
    duplicate = ComplianceRule(
        rule_code="OFFSITE",
        name="站外导流旧版",
        category="站外导流",
        pattern="微信",
        severity="warning",
        guidance="旧版提示。",
        version=1,
        enabled=1,
    )

    assert match_compliance_text("", [older, duplicate]) == []
    assert len(match_compliance_text("请加微信", [older, duplicate])) == 1


def test_enabled_rules_are_detached_snapshots_that_survive_commit(db):
    rule = ComplianceRule(
        rule_code="SNAPSHOT_RULE",
        name="快照规则",
        category="测试",
        pattern="违规词",
        severity="warning",
        guidance="请人工复核。",
        version=1,
        enabled=1,
    )
    db.add(rule)
    db.commit()

    rules = load_enabled_compliance_rules(db)
    db.commit()

    snapshot = next(item for item in rules if item.rule_code == "SNAPSHOT_RULE")
    assert isinstance(snapshot, ComplianceRuleSnapshot)
    assert match_compliance_text("包含违规词", [snapshot])[0]["rule_code"] == (
        "SNAPSHOT_RULE"
    )


def test_dispatch_policy_api_persists_order_mode(client, auth_headers):
    response = client.get("/api/v1/transcripts/dispatch-policy", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["order_mode"] == "smart"
    assert response.json()["auto_scope_timezone"] == "Asia/Shanghai"

    updated = client.put(
        "/api/v1/transcripts/dispatch-policy",
        headers=auth_headers,
        json={"order_mode": "fifo"},
    )
    assert updated.status_code == 200
    assert updated.json()["order_mode"] == "fifo"


def test_transcript_segments_api_attaches_suspected_compliance_hits(
    db, client, auth_headers
):
    session = LiveSession(id=901, room_id=901, anchor_name="测试主播")
    rule = ComplianceRule(
        id=901,
        rule_code="PROMISE_901",
        name="经营承诺",
        category="经营承诺",
        pattern="稳赚不赔",
        severity="critical",
        guidance="请改为基于真实条件的风险提示。",
        version=1,
        enabled=1,
    )
    segment = TranscriptSegment(
        id=901,
        session_id=901,
        segment_start=12,
        segment_end=15,
        text_content="这样开店稳赚不赔",
        segment_type="asr_realtime",
        asr_status="completed",
    )
    db.add_all([session, rule, segment])
    db.commit()

    response = client.get("/api/v1/transcripts/901/segments", headers=auth_headers)

    assert response.status_code == 200
    hit = response.json()[0]["compliance_hits"][0]
    assert hit["matched_keyword"] == "稳赚不赔"
    assert hit["review_status"] == "suspected"
