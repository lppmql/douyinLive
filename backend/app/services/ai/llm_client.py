"""本地 Ollama 大模型客户端（复用 OpenAI 兼容协议）。"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx
import anyio
from openai import AsyncOpenAI, OpenAI

from app.core.config import is_local_ollama_url, settings
from app.services.ai.telemetry import AiCallObservation, record_ai_call

logger = logging.getLogger(__name__)

# OpenAI SDK 要求 api_key 参数非空；Ollama 本地接口会忽略该固定占位值。
# 它不是密钥，不从环境变量读取，也不会被发送到任何云端地址。
OLLAMA_SDK_PLACEHOLDER = "ollama-local"

_client: OpenAI | None = None


def _record_safely(observation: AiCallObservation) -> None:
    """观测链路失败时降级，不能改变本地模型的业务结果。"""
    try:
        record_ai_call(observation)
    except Exception as exc:  # noqa: BLE001 - 观测失败不得阻断业务
        logger.warning("AI调用观测失败，不阻断本地模型结果: %s", exc)


def get_ollama_service_url() -> str:
    """从 OpenAI 兼容地址得到 Ollama 原生服务根地址。"""
    if not is_local_ollama_url(settings.OLLAMA_BASE_URL):
        raise ValueError("Ollama 地址必须是本机回环地址，且路径为 /v1")
    parsed = urlparse(settings.OLLAMA_BASE_URL)
    return urlunparse((parsed.scheme, parsed.netloc, "", "", "", "")).rstrip("/")


def get_local_ai_runtime_status(timeout_seconds: float = 1.5) -> dict[str, Any]:
    """轻量检查 Ollama 服务和目标模型，不触发模型加载。"""
    try:
        response = httpx.get(
            f"{get_ollama_service_url()}/api/tags",
            timeout=max(0.2, timeout_seconds),
            trust_env=False,
            follow_redirects=False,
        )
        response.raise_for_status()
        model_names = {
            str(item.get("name") or item.get("model") or "")
            for item in response.json().get("models", [])
        }
        configured = settings.OLLAMA_MODEL
        model_available = configured in model_names or f"{configured}:latest" in model_names
        return {
            "service_running": True,
            "model_available": model_available,
            "model": configured,
            "message": (
                "本地 Ollama 与模型已就绪"
                if model_available
                else f"Ollama 已运行，但缺少模型 {configured}"
            ),
        }
    except Exception as exc:  # noqa: BLE001 - 健康接口只返回降级状态
        return {
            "service_running": False,
            "model_available": False,
            "model": settings.OLLAMA_MODEL,
            "message": f"本地 Ollama 不可用：{type(exc).__name__}",
        }


def get_client() -> OpenAI:
    """获取只连接本机 Ollama 的 OpenAI 兼容客户端。"""
    global _client
    if _client is None:
        get_ollama_service_url()  # 独立脚本调用也必须经过本机地址校验。
        _client = OpenAI(
            api_key=OLLAMA_SDK_PLACEHOLDER,
            base_url=settings.OLLAMA_BASE_URL,
            timeout=settings.OLLAMA_REQUEST_TIMEOUT_SECONDS,
            max_retries=0,
            # 忽略系统代理并拒绝重定向，防止本机请求被转发到外网。
            http_client=httpx.Client(trust_env=False, follow_redirects=False),
        )
    return _client


def get_async_client() -> AsyncOpenAI:
    """流式请求独立持有异步客户端，断开后可取消等待并释放连接。"""
    get_ollama_service_url()
    return AsyncOpenAI(
        api_key=OLLAMA_SDK_PLACEHOLDER,
        base_url=settings.OLLAMA_BASE_URL,
        timeout=settings.OLLAMA_REQUEST_TIMEOUT_SECONDS,
        max_retries=0,
        http_client=httpx.AsyncClient(trust_env=False, follow_redirects=False),
    )


def chat(
    system_prompt: str,
    user_message: str,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    response_format: dict | None = None,
    operation: str = "chat",
    session_id: int | None = None,
    prompt_name: str | None = None,
    prompt_version: int | None = None,
    response_mode: str = "text",
) -> str:
    """调用本机 Ollama；失败时明确报错，不回退到任何云端服务。"""
    selected_model = model or settings.OLLAMA_MODEL
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    kwargs: dict[str, Any] = {
        "model": selected_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        # 业务要求直接返回正文或 JSON，关闭思考内容可减少空正文和格式漂移。
        "reasoning_effort": "none",
    }
    if response_format:
        kwargs["response_format"] = response_format

    started_at = time.perf_counter()
    input_chars = len(system_prompt) + len(user_message)
    content = ""
    try:
        response = get_client().chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""
        if getattr(response.choices[0], "finish_reason", None) == "length":
            raise ValueError("本地模型输出达到长度上限，请缩小分析范围后重试")
        if not content.strip():
            raise ValueError("本地模型返回了空内容")
        if response_mode == "json":
            if not isinstance(json.loads(content), dict):
                raise ValueError("本地模型 JSON 结果必须是对象")
        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
        _record_safely(
            AiCallObservation(
                operation=operation,
                provider="ollama",
                model_name=selected_model,
                status="success",
                input_chars=input_chars,
                output_chars=len(content),
                latency_ms=round((time.perf_counter() - started_at) * 1000),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                session_id=session_id,
                prompt_name=prompt_name,
                prompt_version=prompt_version,
                response_mode=response_mode,
            )
        )
        logger.info(
            "本地 Ollama 调用成功, 模型=%s 输入长度=%d 输出长度=%d",
            selected_model,
            input_chars,
            len(content),
        )
        return content
    except Exception as exc:
        _record_safely(
            AiCallObservation(
                operation=operation,
                provider="ollama",
                model_name=selected_model,
                status="failed",
                input_chars=input_chars,
                output_chars=len(content),
                latency_ms=round((time.perf_counter() - started_at) * 1000),
                session_id=session_id,
                prompt_name=prompt_name,
                prompt_version=prompt_version,
                response_mode=response_mode,
                error_code=type(exc).__name__,
                error_message=str(exc),
            )
        )
        logger.error("本地 Ollama 调用失败: %s", exc)
        raise


def chat_json(
    system_prompt: str,
    user_message: str,
    model: str | None = None,
    temperature: float = 0.3,
    operation: str = "chat_json",
    session_id: int | None = None,
    prompt_name: str | None = None,
    prompt_version: int | None = None,
) -> dict:
    """调用本地模型并通过 Ollama JSON 模式返回对象。"""
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


async def chat_stream(
    system_prompt: str,
    user_message: str,
    model: str | None = None,
    temperature: float = 0.7,
    operation: str = "chat_stream",
    session_id: int | None = None,
    prompt_name: str | None = None,
    prompt_version: int | None = None,
):
    """流式调用本地 Ollama，用于知识库问答。"""
    selected_model = model or settings.OLLAMA_MODEL
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    started_at = time.perf_counter()
    input_chars = len(system_prompt) + len(user_message)
    output_chars = 0
    stream = None
    client = None
    prompt_tokens = completion_tokens = total_tokens = 0
    try:
        client = get_async_client()
        stream = await client.chat.completions.create(
            model=selected_model,
            messages=messages,
            temperature=temperature,
            reasoning_effort="none",
            max_tokens=4096,
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                prompt_tokens = int(usage.prompt_tokens or 0)
                completion_tokens = int(usage.completion_tokens or 0)
                total_tokens = int(usage.total_tokens or 0)
            if not chunk.choices:
                continue
            if getattr(chunk.choices[0], "finish_reason", None) == "length":
                raise ValueError("本地模型流式输出达到长度上限，请缩小问题范围后重试")
            delta = chunk.choices[0].delta.content or ""
            if delta:
                output_chars += len(delta)
                yield delta
        if not output_chars:
            raise ValueError("本地模型返回了空内容")
        _record_safely(
            AiCallObservation(
                operation=operation,
                provider="ollama",
                model_name=selected_model,
                status="success",
                input_chars=input_chars,
                output_chars=output_chars,
                latency_ms=round((time.perf_counter() - started_at) * 1000),
                session_id=session_id,
                prompt_name=prompt_name,
                prompt_version=prompt_version,
                response_mode="stream",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )
        )
    except (GeneratorExit, asyncio.CancelledError):
        _record_safely(
            AiCallObservation(
                operation=operation,
                provider="ollama",
                model_name=selected_model,
                status="cancelled",
                input_chars=input_chars,
                output_chars=output_chars,
                latency_ms=round((time.perf_counter() - started_at) * 1000),
                session_id=session_id,
                prompt_name=prompt_name,
                prompt_version=prompt_version,
                response_mode="stream",
            )
        )
        raise
    except Exception as exc:
        _record_safely(
            AiCallObservation(
                operation=operation,
                provider="ollama",
                model_name=selected_model,
                status="failed",
                input_chars=input_chars,
                output_chars=output_chars,
                latency_ms=round((time.perf_counter() - started_at) * 1000),
                session_id=session_id,
                prompt_name=prompt_name,
                prompt_version=prompt_version,
                response_mode="stream",
                error_code=type(exc).__name__,
                error_message=str(exc),
            )
        )
        logger.error("本地 Ollama 流式调用失败: %s", exc)
        raise
    finally:
        # 断开信号会取消当前任务，清理阶段短暂屏蔽取消，保证 HTTP 连接真正释放。
        with anyio.CancelScope(shield=True):
            try:
                if stream is not None:
                    await stream.close()
            finally:
                if client is not None:
                    await client.close()
