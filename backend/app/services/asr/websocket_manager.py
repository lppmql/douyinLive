"""
WebSocket 连接管理器 + Redis Pub/Sub 桥接

架构:
  ASR Worker -> Redis Pub -> FastAPI Redis Sub -> Browser WebSocket

管理所有前端的 WebSocket 连接，通过 Redis Pub/Sub 接收 ASR 结果并广播。
"""
import asyncio
import json
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

    async def connect(self, session_id: int, ws: WebSocket):
        """注册前端 WebSocket 连接"""
        if session_id not in self._connections:
            self._connections[session_id] = set()
            # 首次有连接时启动该 session 的 Redis 订阅
            await self._start_listener(session_id)
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

    async def _start_listener(self, session_id: int):
        """启动 Redis Pub/Sub 监听"""
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

        # 每个 session 一个监听任务
        asyncio.create_task(_listen())

    async def close(self):
        """关闭所有连接"""
        for session_id in list(self._connections.keys()):
            for ws in self._connections[session_id]:
                try:
                    await ws.close()
                except Exception:
                    pass
        self._connections.clear()
        if self._redis:
            await self._redis.close()


# 全局单例
ws_manager = WebSocketManager()
