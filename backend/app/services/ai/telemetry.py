"""Langfuse-lite 风格的 AI 调用元数据记录。"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

from app.core.config import settings
from app.core.observability import (
    AI_CALL_DURATION,
    AI_CALLS_TOTAL,
    AI_LAST_SUCCESS,
    AI_TOKENS_TOTAL,
    new_trace_id,
    trace_id_var,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AiCallObservation:
    operation: str
    model_name: str
    status: str
    input_chars: int
    output_chars: int
    latency_ms: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    provider: str = "deepseek"
    response_mode: str = "text"
    session_id: int | None = None
    prompt_name: str | None = None
    prompt_version: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    trace_id: str | None = None


def _label(value: str | None, fallback: str, max_length: int = 50) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "_", (value or "").strip()).strip("_")
    return (normalized or fallback)[:max_length]


def _safe_error_message(message: str | None) -> str | None:
    if not message:
        return None
    sanitized = str(message)
    for secret in (settings.DEEPSEEK_API_KEY, settings.DB_PASSWORD, settings.JWT_SECRET_KEY):
        if secret:
            sanitized = sanitized.replace(secret, "[REDACTED]")
    return sanitized[:500]


def _current_trace_id(explicit: str | None) -> str:
    candidate = explicit or trace_id_var.get()
    return new_trace_id(candidate if candidate != "-" else None)


def record_ai_call(observation: AiCallObservation) -> None:
    """记录低基数指标和数据库元数据；观测失败不能影响业务调用。"""
    operation = _label(observation.operation, "chat")
    model_name = _label(observation.model_name, "unknown", 100)
    status = _label(observation.status, "failed", 20)
    trace_id = _current_trace_id(observation.trace_id)
    latency_seconds = max(0, observation.latency_ms) / 1000

    AI_CALLS_TOTAL.labels(operation=operation, model=model_name, status=status).inc()
    AI_CALL_DURATION.labels(operation=operation, model=model_name).observe(latency_seconds)
    AI_TOKENS_TOTAL.labels(operation=operation, model=model_name, direction="prompt").inc(
        max(0, observation.prompt_tokens)
    )
    AI_TOKENS_TOTAL.labels(operation=operation, model=model_name, direction="completion").inc(
        max(0, observation.completion_tokens)
    )
    if status == "success":
        AI_LAST_SUCCESS.set(time.time())

    try:
        from app.core.database import SessionLocal
        from app.models.ai_call_traces import AiCallTrace

        db = SessionLocal()
        try:
            db.add(
                AiCallTrace(
                    trace_id=trace_id,
                    session_id=observation.session_id,
                    operation=operation,
                    provider=_label(observation.provider, "unknown", 32),
                    model_name=model_name,
                    prompt_name=_label(observation.prompt_name, "", 50) or None,
                    prompt_version=observation.prompt_version,
                    response_mode=_label(observation.response_mode, "text", 20),
                    status=status,
                    input_chars=max(0, observation.input_chars),
                    output_chars=max(0, observation.output_chars),
                    prompt_tokens=max(0, observation.prompt_tokens),
                    completion_tokens=max(0, observation.completion_tokens),
                    total_tokens=max(0, observation.total_tokens),
                    latency_ms=max(0, observation.latency_ms),
                    error_code=_label(observation.error_code, "", 100) or None,
                    error_message=_safe_error_message(observation.error_message),
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    except Exception as exc:
        logger.warning("AI调用追踪写入失败，不阻断业务: %s", exc)
