"""
FunASR WebSocket 客户端 — 连接 FunASR 服务进行实时语音识别

支持两种模式:
  - realtime: 通过 WebSocket 连接 FunASR 服务
  - mock: 离线模式，返回模拟识别结果
"""
import asyncio
import json
from typing import AsyncGenerator, Optional

import websockets
from websockets.protocol import State

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
            if settings.asr_mock_enabled:
                logger.warning("已显式开启 ASR_ALLOW_MOCK，将使用模拟识别结果")
            return False

    @property
    def connected(self) -> bool:
        return self._ws is not None and self._ws.state is State.OPEN

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
            if not settings.asr_mock_enabled:
                raise RuntimeError(
                    f"真实 FunASR 服务不可用: {self.ws_url}；任务已停止，未写入模拟话术"
                )
            async for result in self._mock_transcribe(pcm_frames):
                yield result
            return

        async for result in self._realtime_transcribe(pcm_frames):
            yield result

    async def _realtime_transcribe(
        self, pcm_frames: AsyncGenerator[bytes, None]
    ) -> AsyncGenerator[dict, None]:
        """真实 FunASR WebSocket 转写"""
        result_queue: asyncio.Queue = asyncio.Queue()
        receiver_task = None

        async def receive_results():
            try:
                async for response in self._ws:
                    if isinstance(response, bytes):
                        continue
                    await result_queue.put(json.loads(response))
            except websockets.ConnectionClosed:
                pass

        def normalize_result(data: dict, elapsed_seconds: float) -> Optional[dict]:
            text = str(data.get("text") or "").strip()
            mode = data.get("mode")
            # 2pass-online 是尚未精修的临时结果；只保存最终离线结果，避免重复话术。
            if not text or mode in {"online", "2pass-online"}:
                return None

            start = max(0.0, elapsed_seconds - 3.0)
            end = elapsed_seconds
            timestamp = data.get("timestamp")
            if isinstance(timestamp, str):
                try:
                    timestamp = json.loads(timestamp)
                except json.JSONDecodeError:
                    timestamp = None
            if isinstance(timestamp, list) and timestamp:
                first = timestamp[0]
                last = timestamp[-1]
                if isinstance(first, (list, tuple)) and len(first) >= 2:
                    start = float(first[0]) / 1000
                    if isinstance(last, (list, tuple)) and len(last) >= 2:
                        end = float(last[1]) / 1000

            return {
                "text": text,
                "segment_start": start,
                "segment_end": max(start, end),
                "is_final": bool(data.get("is_final", mode in {"offline", "2pass-offline"})),
            }

        try:
            await self._ws.send(json.dumps({
                "mode": "2pass",
                "chunk_size": [5, 10, 5],
                "chunk_interval": 10,
                "encoder_chunk_look_back": 4,
                "decoder_chunk_look_back": 0,
                "audio_fs": settings.ASR_SAMPLE_RATE,
                "wav_name": str(self._session_id),
                "wav_format": "pcm",
                "is_speaking": True,
                "hotwords": "",
                "itn": True,
            }))
            receiver_task = asyncio.create_task(receive_results())

            frame_count = 0
            async for frame in pcm_frames:
                frame_count += 1
                await self._ws.send(frame)
                await asyncio.sleep(0.005)

                while not result_queue.empty():
                    result = normalize_result(
                        result_queue.get_nowait(), frame_count * 0.06
                    )
                    if result:
                        yield result

            await self._ws.send(json.dumps({"is_speaking": False}))
            # 流结束后，离线精修结果可能稍晚到达。
            while True:
                try:
                    data = await asyncio.wait_for(result_queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    break
                result = normalize_result(data, frame_count * 0.06)
                if result:
                    yield result
                if data.get("is_final"):
                    break
        except websockets.ConnectionClosed:
            logger.warning("FunASR 连接断开")
        except Exception as e:
            logger.error(f"FunASR 转写出错: {e}")
            raise
        finally:
            if receiver_task:
                receiver_task.cancel()
                try:
                    await receiver_task
                except asyncio.CancelledError:
                    pass

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
        if self.connected:
            await self._ws.close()
