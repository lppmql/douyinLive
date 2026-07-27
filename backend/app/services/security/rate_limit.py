"""基于 Redis 的轻量限流。

限流就是“在一段时间内最多允许多少次请求”。登录和验证码同时按来源地址、
账号或手机号限制，避免攻击者反复猜密码或验证码。
"""

from __future__ import annotations

import hashlib

from redis import Redis

from app.core.config import settings


class RateLimitExceeded(Exception):
    """请求次数超过安全上限。"""


def privacy_key(value: str) -> str:
    """把手机号、账号或地址转成不可逆摘要，Redis 键中不保存个人信息。"""
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


def _redis_client() -> Redis:
    return Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )


def hit_rate_limit(bucket: str, identity: str, *, limit: int, window_seconds: int) -> int:
    """记录一次请求；超过上限时抛出异常，并返回当前次数。"""
    key = f"security:rate:{bucket}:{privacy_key(identity)}"
    client = _redis_client()
    try:
        pipeline = client.pipeline()
        pipeline.incr(key)
        pipeline.ttl(key)
        count, ttl = pipeline.execute()
        if int(ttl) < 0:
            client.expire(key, window_seconds)
        if int(count) > limit:
            raise RateLimitExceeded("请求过于频繁，请稍后再试")
        return int(count)
    finally:
        client.close()


def clear_rate_limit(bucket: str, identity: str) -> None:
    """验证成功后清除对应失败计数。"""
    client = _redis_client()
    try:
        client.delete(f"security:rate:{bucket}:{privacy_key(identity)}")
    finally:
        client.close()
