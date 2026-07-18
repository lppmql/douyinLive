from types import SimpleNamespace

import pytest

from app.core import database
from app.core.config import settings
from app.services.ai import deepseek_client
from app.services.ai.telemetry import AiCallObservation, record_ai_call


class FakeCompletions:
    def __init__(self, content: str):
        self.content = content

    def create(self, **_kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))],
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=7, total_tokens=19),
        )


def fake_client(content: str):
    return SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(content)))


def test_json_call_records_prompt_version_and_token_metadata(monkeypatch):
    observations = []
    monkeypatch.setattr(deepseek_client, "get_client", lambda: fake_client('{"score": 88}'))
    monkeypatch.setattr(deepseek_client, "record_ai_call", observations.append)

    result = deepseek_client.chat_json(
        system_prompt="只依据真实话术评分",
        user_message="真实话术内容",
        operation="speech_score",
        session_id=13261,
        prompt_name="speech_score",
        prompt_version=3,
    )

    assert result == {"score": 88}
    assert len(observations) == 1
    observation = observations[0]
    assert observation.status == "success"
    assert observation.session_id == 13261
    assert observation.prompt_name == "speech_score"
    assert observation.prompt_version == 3
    assert observation.prompt_tokens == 12
    assert observation.completion_tokens == 7
    assert observation.total_tokens == 19
    assert not hasattr(observation, "input_text")
    assert not hasattr(observation, "output_text")


def test_invalid_json_is_recorded_as_failed_call(monkeypatch):
    observations = []
    monkeypatch.setattr(deepseek_client, "get_client", lambda: fake_client("不是JSON"))
    monkeypatch.setattr(deepseek_client, "record_ai_call", observations.append)

    with pytest.raises(ValueError):
        deepseek_client.chat_json(
            system_prompt="返回JSON",
            user_message="分析真实数据",
            operation="anomaly_detection",
            session_id=13261,
        )

    assert len(observations) == 1
    assert observations[0].status == "failed"
    assert observations[0].error_code == "JSONDecodeError"


def test_telemetry_failure_does_not_change_successful_ai_result(monkeypatch):
    monkeypatch.setattr(deepseek_client, "get_client", lambda: fake_client("正常回答"))

    def fail_telemetry(_observation):
        raise RuntimeError("观测库暂时不可用")

    monkeypatch.setattr(deepseek_client, "record_ai_call", fail_telemetry)

    result = deepseek_client.chat(
        system_prompt="只依据真实数据",
        user_message="总结本场直播",
        operation="session_summary",
    )

    assert result == "正常回答"


def test_trace_storage_redacts_secrets_and_only_saves_metadata(monkeypatch):
    saved = []

    class FakeDb:
        def add(self, row):
            saved.append(row)

        def commit(self):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(database, "SessionLocal", FakeDb)
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "never-store-this-key")

    record_ai_call(AiCallObservation(
        operation="knowledge_qa",
        model_name="deepseek-chat",
        status="failed",
        input_chars=1234,
        output_chars=0,
        latency_ms=456,
        prompt_name="qa",
        prompt_version=2,
        error_code="ApiError",
        error_message="request failed with never-store-this-key",
        trace_id="real-trace-123",
    ))

    assert len(saved) == 1
    row = saved[0]
    assert row.trace_id == "real-trace-123"
    assert row.input_chars == 1234
    assert row.prompt_version == 2
    assert "never-store-this-key" not in row.error_message
    assert "[REDACTED]" in row.error_message
    assert not hasattr(row, "input_text")
    assert not hasattr(row, "output_text")
