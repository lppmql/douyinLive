"""DeepSeek API 客户端（OpenAI 兼容 SDK）"""
import json
import logging
import time
from typing import Any

from openai import OpenAI

from app.core.config import settings
from app.services.ai.telemetry import AiCallObservation, record_ai_call

logger = logging.getLogger(__name__)

# 全局客户端（懒初始化）
_client: OpenAI | None = None


def _record_safely(observation: AiCallObservation) -> None:
    """观测链路必须降级，不能反向改变模型调用结果。"""
    try:
        record_ai_call(observation)
    except Exception as exc:
        logger.warning("AI调用观测失败，不阻断模型结果: %s", exc)


def get_client() -> OpenAI:
    """获取 DeepSeek 客户端（单例）"""
    global _client
    if _client is None:
        if not settings.DEEPSEEK_API_KEY:
            raise ValueError("DEEPSEEK_API_KEY 未配置")
        _client = OpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_API_URL,
        )
    return _client


def chat(
    system_prompt: str,
    user_message: str,
    model: str = "deepseek-chat",
    temperature: float = 0.7,
    max_tokens: int = 4096,
    response_format: dict | None = None,
    operation: str = "chat",
    session_id: int | None = None,
    prompt_name: str | None = None,
    prompt_version: int | None = None,
    response_mode: str = "text",
) -> str:
    """调用 DeepSeek Chat 补全

    Args:
        system_prompt: 系统提示词
        user_message: 用户消息
        model: 模型名，默认 deepseek-chat
        temperature: 温度
        max_tokens: 最大输出 token
        response_format: 响应格式，如 {"type": "json_object"}

    Returns:
        模型回复文本
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        kwargs["response_format"] = response_format

    started_at = time.perf_counter()
    input_chars = len(system_prompt) + len(user_message)
    content = ""
    try:
        client = get_client()
        resp = client.chat.completions.create(**kwargs)
        content = resp.choices[0].message.content or ""
        if response_mode == "json":
            json.loads(content)
        usage = getattr(resp, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
        latency_ms = round((time.perf_counter() - started_at) * 1000)
        _record_safely(AiCallObservation(
            operation=operation,
            model_name=model,
            status="success",
            input_chars=input_chars,
            output_chars=len(content),
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            session_id=session_id,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            response_mode=response_mode,
        ))
        logger.info("DeepSeek API 调用成功, 输入长度=%d, 输出长度=%d",
                     input_chars, len(content))
        return content
    except Exception as e:
        _record_safely(AiCallObservation(
            operation=operation,
            model_name=model,
            status="failed",
            input_chars=input_chars,
            output_chars=len(content),
            latency_ms=round((time.perf_counter() - started_at) * 1000),
            session_id=session_id,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            response_mode=response_mode,
            error_code=type(e).__name__,
            error_message=str(e),
        ))
        logger.error("DeepSeek API 调用失败: %s", e)
        raise


def chat_json(
    system_prompt: str,
    user_message: str,
    model: str = "deepseek-chat",
    temperature: float = 0.3,
    operation: str = "chat_json",
    session_id: int | None = None,
    prompt_name: str | None = None,
    prompt_version: int | None = None,
) -> dict:
    """调用 DeepSeek 并返回 JSON 对象"""
    content = chat(
        system_prompt=system_prompt,
        user_message=user_message,
        model=model,
        temperature=temperature,
        response_format={"type": "json_object"},
        operation=operation,
        session_id=session_id,
        prompt_name=prompt_name,
        prompt_version=prompt_version,
        response_mode="json",
    )
    return json.loads(content)


def chat_stream(
    system_prompt: str,
    user_message: str,
    model: str = "deepseek-chat",
    temperature: float = 0.7,
    operation: str = "chat_stream",
    session_id: int | None = None,
    prompt_name: str | None = None,
    prompt_version: int | None = None,
):
    """流式调用 DeepSeek，返回迭代器"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    started_at = time.perf_counter()
    input_chars = len(system_prompt) + len(user_message)
    output_chars = 0
    try:
        client = get_client()
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                output_chars += len(delta)
                yield delta
        _record_safely(AiCallObservation(
            operation=operation,
            model_name=model,
            status="success",
            input_chars=input_chars,
            output_chars=output_chars,
            latency_ms=round((time.perf_counter() - started_at) * 1000),
            session_id=session_id,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            response_mode="stream",
        ))
    except GeneratorExit:
        _record_safely(AiCallObservation(
            operation=operation,
            model_name=model,
            status="cancelled",
            input_chars=input_chars,
            output_chars=output_chars,
            latency_ms=round((time.perf_counter() - started_at) * 1000),
            session_id=session_id,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            response_mode="stream",
        ))
        raise
    except Exception as e:
        _record_safely(AiCallObservation(
            operation=operation,
            model_name=model,
            status="failed",
            input_chars=input_chars,
            output_chars=output_chars,
            latency_ms=round((time.perf_counter() - started_at) * 1000),
            session_id=session_id,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            response_mode="stream",
            error_code=type(e).__name__,
            error_message=str(e),
        ))
        logger.error("DeepSeek 流式调用失败: %s", e)
        raise
