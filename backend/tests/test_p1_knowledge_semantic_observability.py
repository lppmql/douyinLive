from datetime import datetime, timedelta
from types import SimpleNamespace

from app.core.observability import new_trace_id
from app.services.ai.time_slice_service import _slice_payload, format_offset
from app.services.metrics.semantic import METRIC_DEFINITIONS, SEMANTIC_DATASETS


def test_time_slice_only_maps_comments_inside_platform_time_window():
    live_start = datetime(2026, 7, 15, 10, 0, 0)
    session = SimpleNamespace(
        id=100,
        live_start_time=live_start,
        anchor_name="真实主播",
        anchor_nickname=None,
        session_title="真实直播",
    )
    comments = [
        SimpleNamespace(
            comment_time=live_start + timedelta(seconds=299),
            user_nickname="用户A",
            is_high_intent=1,
            comment_content="第一片评论",
        ),
        SimpleNamespace(
            comment_time=live_start + timedelta(seconds=300),
            user_nickname="用户B",
            is_high_intent=0,
            comment_content="第二片评论",
        ),
    ]

    first = _slice_payload(session, 0, 300, 600, [], comments, [], 0)
    second = _slice_payload(session, 1, 300, 600, [], comments, [], 0)

    assert first["comment_count"] == 1
    assert "第一片评论" in first["comments_text"]
    assert "第二片评论" not in first["comments_text"]
    assert second["comment_count"] == 1
    assert "第二片评论" in second["comments_text"]


def test_unmapped_comment_count_does_not_fabricate_comment_content():
    session = SimpleNamespace(
        id=101,
        live_start_time=None,
        anchor_name="真实主播",
        anchor_nickname=None,
        session_title="缺少开播时间",
    )
    comment = SimpleNamespace(
        comment_time=None,
        user_nickname="用户A",
        is_high_intent=0,
        comment_content="无法精确归属",
    )

    payload = _slice_payload(session, 0, 300, 300, [], [comment], [], 1)

    assert payload["unmapped_comment_count"] == 1
    assert payload["comment_count"] == 0
    assert payload["comments_text"] is None


def test_semantic_layer_has_unique_metrics_and_readonly_views():
    metric_keys = [item["key"] for item in METRIC_DEFINITIONS]
    dataset_views = [item["view"] for item in SEMANTIC_DATASETS]

    assert len(metric_keys) == len(set(metric_keys))
    assert all(item["time_semantics"] for item in METRIC_DEFINITIONS)
    assert len(dataset_views) == 7
    assert all(view.startswith("de_v_") for view in dataset_views)


def test_trace_id_reuses_valid_header_and_rejects_unsafe_value():
    assert new_trace_id("collector-trace-123") == "collector-trace-123"
    generated = new_trace_id("bad trace/id")
    assert generated != "bad trace/id"
    assert len(generated) == 32
    assert format_offset(3661) == "01:01:01"
