"""DeepSeek API 客户端（OpenAI 兼容 SDK）"""
import json
import logging
from typing import Any

from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

# 全局客户端（懒初始化）
_client: OpenAI | None = None


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
    client = get_client()
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

    try:
        resp = client.chat.completions.create(**kwargs)
        content = resp.choices[0].message.content or ""
        logger.info("DeepSeek API 调用成功, 输入长度=%d, 输出长度=%d",
                     len(system_prompt) + len(user_message), len(content))
        return content
    except Exception as e:
        logger.error("DeepSeek API 调用失败: %s", e)
        raise


def chat_json(
    system_prompt: str,
    user_message: str,
    model: str = "deepseek-chat",
    temperature: float = 0.3,
) -> dict:
    """调用 DeepSeek 并返回 JSON 对象"""
    content = chat(
        system_prompt=system_prompt,
        user_message=user_message,
        model=model,
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    return json.loads(content)


def chat_stream(
    system_prompt: str,
    user_message: str,
    model: str = "deepseek-chat",
    temperature: float = 0.7,
):
    """流式调用 DeepSeek，返回迭代器"""
    client = get_client()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    try:
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                yield delta
    except Exception as e:
        logger.error("DeepSeek 流式调用失败: %s", e)
        raise
