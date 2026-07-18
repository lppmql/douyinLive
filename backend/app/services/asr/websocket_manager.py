"""
WebSocket 连接管理器 + Redis Pub/Sub 桥接

架构:
  ASR Worker -> Redis Pub -> FastAPI Redis Sub -> Browser WebSocket

管理所有前端的 WebSocket 连接，通过 Redis Pub/Sub 接收 ASR 结果并广播。
"""
import asyncio
import json
from contextlib import suppress
from typing import Optional

import redis.asyncio as aioredis
from fastapi import WebSocket

from app.core.config import settings
from app.core.logger import logger


REDIS_CHANNEL_ASR = "asr:transcript"


class WebSocketManager:
    """
    WebSocket 连接管理器

    按 session_id 分组管理多个前端连接，支持广播和 Redis Pub/Sub 订阅。
    """

    def __init__(self):
        self._connections: dict[int, set[WebSocket]] = {}
        self._redis: Optional[aioredis.Redis] = None
        self._pubsub_task: Optional[asyncio.Task] = None
        self._listener_lock = asyncio.Lock()

    async def connect(self, session_id: int, ws: WebSocket):
        """注册前端 WebSocket 连接"""
        if session_id not in self._connections:
            self._connections[session_id] = set()
        await self._ensure_listener()
        self._connections[session_id].add(ws)
        logger.info(f"WebSocket 已连接: session={session_id} 当前连接数={len(self._connections[session_id])}")

    async def disconnect(self, session_id: int, ws: WebSocket):
        """移除前端 WebSocket 连接"""
        if session_id in self._connections:
            self._connections[session_id].discard(ws)
            if not self._connections[session_id]:
                del self._connections[session_id]
                logger.info(f"WebSocket 断开: session={session_id} 无剩余连接")

    async def broadcast(self, session_id: int, data: dict):
        """向某 session 的所有前端广播消息"""
        if session_id not in self._connections:
            return
        message = json.dumps(data, ensure_ascii=False)
        disconnected = set()
        for ws in self._connections[session_id]:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.add(ws)
        for ws in disconnected:
            await self.disconnect(session_id, ws)

    async def publish_asr_result(self, session_id: int, data: dict):
        """通过 Redis 发布 ASR 转写结果"""
        if not self._redis:
            try:
                self._redis = aioredis.from_url(settings.REDIS_URL)
            except Exception as e:
                logger.warning(f"Redis 连接失败: {e}")
                return
        payload = json.dumps({"session_id": session_id, **data}, ensure_ascii=False)
        try:
            await self._redis.publish(REDIS_CHANNEL_ASR, payload)
        except Exception as e:
            logger.warning(f"Redis Pub 失败: {e}")

    async def _ensure_listener(self):
        """确保进程内只有一个 Redis 订阅，避免多场连接导致重复广播。"""
        if self._pubsub_task and not self._pubsub_task.done():
            return
        async with self._listener_lock:
            if self._pubsub_task and not self._pubsub_task.done():
                return
            await self._start_listener()

    async def _start_listener(self):
        """启动全局 Redis Pub/Sub 监听。"""
        if not self._redis:
            try:
                self._redis = aioredis.from_url(settings.REDIS_URL)
            except Exception:
                return

        pubsub = self._redis.pubsub()
        await pubsub.subscribe(REDIS_CHANNEL_ASR)

        async def _listen():
            try:
                async for message in pubsub.listen():
                    if message["type"] != "message":
                        continue
                    try:
                        data = json.loads(message["data"])
                        sid = data.pop("session_id", None)
                        if sid is not None:
                            await self.broadcast(sid, data)
                    except json.JSONDecodeError:
                        pass
            except asyncio.CancelledError:
                pass
            finally:
                await pubsub.unsubscribe(REDIS_CHANNEL_ASR)
                await pubsub.close()

        self._pubsub_task = asyncio.create_task(_listen())

    async def close(self):
        """关闭所有连接"""
        for session_id in list(self._connections.keys()):
            for ws in self._connections[session_id]:
                try:
                    await ws.close()
                except Exception:
                    pass
        self._connections.clear()
        if self._pubsub_task:
            self._pubsub_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._pubsub_task
            self._pubsub_task = None
        if self._redis:
            await self._redis.close()
            self._redis = None


# 全局单例
ws_manager = WebSocketManager()
