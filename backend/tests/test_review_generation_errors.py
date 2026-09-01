"""AI 复盘接口的可恢复错误映射测试。"""

import pytest
from fastapi import HTTPException

from app.api.v1 import reviews
from app.services.ai.unified_review import LocalAiUnavailableError


def test_generate_review_maps_local_ai_outage_to_service_unavailable(monkeypatch):
    monkeypatch.setattr(reviews, "generate_findings", lambda *_args: [])
    monkeypatch.setattr(
        reviews,
        "generate_unified_review",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            LocalAiUnavailableError("本地 AI 暂时不可用，已自动重试")
        ),
    )

    with pytest.raises(HTTPException) as raised:
        reviews.generate_session_review(2601, db=object())

    assert raised.value.status_code == 503
    assert "已自动重试" in raised.value.detail
