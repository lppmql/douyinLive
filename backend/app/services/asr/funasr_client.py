"""
FunASR WebSocket 客户端 — 连接 FunASR 服务进行实时语音识别

支持两种模式:
  - realtime: 通过 WebSocket 连接 FunASR 服务
  - mock: 离线模式，返回模拟识别结果
"""
import asyncio
import json
import random
from typing import AsyncGenerator, Optional

import websockets

from app.core.config import settings
from app.core.logger import logger


# 模拟话术片段（供 mock 模式使用）
_MOCK_TRANSCRIPTS = [
    "欢迎各位来到我们的直播间",
    "今天给大家带来几款非常超值的商品",
    "先给大家介绍一下今天的福利机制",
    "大家可以看到这款产品的质量非常好",
    "现在下单可以享受限时优惠价",
    "有需要的宝宝可以点击下方小黄车",
    "感谢大家的支持，我们继续看下一款",
    "这款产品的主要特点我已经介绍完了",
    "大家有任何问题可以在评论区提问",
    "最后再给大家一个限时福利",
]


class FunasrClient:
    """
    FunASR WebSocket 客户端

    用法:
        client = FunasrClient()
        async for result in client.transcribe(session_id):
            # result: {"text": str, "segment_start": float, "segment_end": float}
            print(result["text"])
    """

    def __init__(self, ws_url: str = ""):
        self.ws_url = ws_url or settings.FUNASR_WS_URL
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._session_id: int = 0

    async def connect(self) -> bool:
        """连接到 FunASR WebSocket 服务"""
        try:
            self._ws = await websockets.connect(
                self.ws_url,
                ping_interval=30,
                max_size=10_485_760,  # 10MB
            )
            logger.info(f"FunASR 已连接: {self.ws_url}")
            return True
        except Exception as e:
            logger.warning(f"FunASR 连接失败 ({self.ws_url}): {e}")
            logger.warning("将使用 Mock 模式进行语音识别")
            return False

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    async def transcribe(
        self, session_id: int, pcm_frames: AsyncGenerator[bytes, None]
    ) -> AsyncGenerator[dict, None]:
        """
        实时转写 PCM 流

        Args:
            session_id: 直播场次 ID
            pcm_frames: PCM s16le 帧异步生成器

        Yields:
            dict: {"text": str, "segment_start": float, "segment_end": float, "is_final": bool}
        """
        self._session_id = session_id

        if not self.connected:
            # Mock 模式
            async for result in self._mock_transcribe(pcm_frames):
                yield result
            return

        async for result in self._realtime_transcribe(pcm_frames):
            yield result

    async def _realtime_transcribe(
        self, pcm_frames: AsyncGenerator[bytes, None]
    ) -> AsyncGenerator[dict, None]:
        """真实 FunASR WebSocket 转写"""
        try:
            async for frame in pcm_frames:
                await self._ws.send(frame)

                # 非阻塞接收结果
                try:
                    resp = await asyncio.wait_for(self._ws.recv(), timeout=0.1)
                    if isinstance(resp, bytes):
                        continue
                    data = json.loads(resp)
                    text = data.get("text", "").strip()
                    if text:
                        yield {
                            "text": text,
                            "segment_start": data.get("timestamp", [0, 0])[0],
                            "segment_end": data.get("timestamp", [0, 0])[1],
                            "is_final": data.get("is_final", False),
                        }
                except asyncio.TimeoutError:
                    continue
        except websockets.ConnectionClosed:
            logger.warning("FunASR 连接断开")
        except Exception as e:
            logger.error(f"FunASR 转写出错: {e}")

    async def _mock_transcribe(
        self, pcm_frames: AsyncGenerator[bytes, None]
    ) -> AsyncGenerator[dict, None]:
        """Mock 模式 — 模拟识别结果"""
        frame_count = 0
        async for _ in pcm_frames:
            frame_count += 1
            # 每 100 帧（约 6 秒）输出一条模拟话术
            if frame_count % 100 == 0:
                idx = min(frame_count // 100 - 1, len(_MOCK_TRANSCRIPTS) - 1)
                yield {
                    "text": _MOCK_TRANSCRIPTS[idx],
                    "segment_start": (frame_count // 100) * 6,
                    "segment_end": (frame_count // 100) * 6 + 3,
                    "is_final": True,
                }

    async def close(self):
        """关闭连接"""
        if self._ws and not self._ws.closed:
            await self._ws.close()
