from types import SimpleNamespace

from app.services.ai.high_intent_service import _match_real_comment
from app.services.ai.review_service import build_domain_coverage


def test_high_intent_prefers_real_comment_index():
    comments = [
        SimpleNamespace(id=11, user_nickname="同名用户"),
        SimpleNamespace(id=12, user_nickname="同名用户"),
    ]

    matched = _match_real_comment(comments, {"comment_index": 2, "user_name": "同名用户"})

    assert matched.id == 12


def test_high_intent_rejects_ambiguous_or_partial_nickname():
    comments = [
        SimpleNamespace(id=11, user_nickname="开店老板"),
        SimpleNamespace(id=12, user_nickname="开店老板"),
    ]

    assert _match_real_comment(comments, {"user_name": "开店老板"}) is None
    assert _match_real_comment(comments, {"user_name": "老板"}) is None


def test_domain_coverage_uses_transcript_evidence_only():
    segments = [
        SimpleNamespace(segment_start=30, text_content="开店预算要先算房租、装修和货架。"),
        SimpleNamespace(segment_start=90, text_content="需要清单的老板可以主动站内私信。"),
    ]

    coverage = {item["category"]: item for item in build_domain_coverage(segments)}

    assert coverage["预算测算"]["segment_count"] == 1
    assert coverage["资料钩子"]["segment_count"] == 1
    assert coverage["私信承接"]["segment_count"] == 1
    assert coverage["供应链"]["covered"] is False
