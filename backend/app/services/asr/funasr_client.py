"""FunASR WebSocket 客户端。

直播中使用 ``online`` 协议边说边出初稿；下播后使用 ``offline`` 协议
重新生成最终稿。这里的“双通道”不是给任务换个名字，而是会向 FunASR
发送不同的协议配置和不同的音频发送节奏。
"""
import asyncio
import json
from typing import AsyncGenerator, Optional

import websockets
from websockets.protocol import State

from app.core.config import settings
from app.core.logger import logger
from app.services.asr.hotwords import get_hotwords_cached


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


class RealtimeDraftBuffer:
    """把在线模型逐字返回的小碎片合成一条可读初稿。

    FunASR 双通道服务通常会在说话停顿时返回一条带标点的离线修正版；
    如果某个部署只返回在线结果，本缓冲区也会每 10 秒或 80 个字输出一次，
    因此直播初稿不会因为过滤碎片而变成空白。
    """

    MAX_WAIT_SECONDS = 10.0
    MAX_TEXT_LENGTH = 80

    def __init__(self) -> None:
        self._text = ""
        self._started_at: float | None = None
        self._segment_start = 0.0
        # 有些 FunASR 版本会一直返回“从本句开头到现在”的累计文本。
        # 记住已经落盘的前缀，下一次只保存新增后缀，避免每 10 秒重复整句。
        self._emitted_text = ""
        self._last_emitted_end = 0.0

    def push(self, result: dict, response_mode: str | None, elapsed_seconds: float) -> Optional[dict]:
        """加入一次识别响应；准备好完整句子时返回，否则继续等待。"""
        if response_mode not in {"online", "2pass-online"}:
            # 停顿后的修正版比逐字碎片更完整，优先展示它并清空临时缓冲。
            self.clear()
            result["is_final"] = True
            return result

        text = str(result.get("text") or "")
        if not text:
            return None

        # 如果服务端返回的是累计文本，先扣掉已经落盘的部分。
        # 收到落后于当前进度的旧响应时直接等待下一条，不能重复写入。
        if self._emitted_text:
            if text.startswith(self._emitted_text):
                text = text[len(self._emitted_text) :]
            elif self._emitted_text.startswith(text):
                return None
        if not text:
            return None

        if self._started_at is None:
            self._started_at = elapsed_seconds
            self._segment_start = max(
                float(result.get("segment_start") or 0),
                self._last_emitted_end,
            )

        # 不同 FunASR 版本可能返回“新增片段”或“从句首累计到现在”。
        # 两种格式都兼容，避免把累计文本重复拼接。
        if text.startswith(self._text):
            self._text = text
        elif not self._text.endswith(text):
            self._text += text

        waited = elapsed_seconds - self._started_at
        if waited >= self.MAX_WAIT_SECONDS or len(self._text) >= self.MAX_TEXT_LENGTH:
            return self.flush(elapsed_seconds)
        return None

    def flush(self, elapsed_seconds: float) -> Optional[dict]:
        """流结束或等待到上限时，把剩余真实文字作为临时初稿输出。"""
        text = self._text.strip()
        if not text:
            self.clear()
            return None
        result = {
            "text": text,
            "segment_start": self._segment_start,
            "segment_end": max(self._segment_start, elapsed_seconds),
            "is_final": False,
        }
        self._emitted_text += text
        self._last_emitted_end = float(result["segment_end"])
        self._clear_pending()
        return result

    def clear(self) -> None:
        """开始新句子时清空累计历史；离线修正版已经替代当前在线草稿。"""
        self._clear_pending()
        self._emitted_text = ""
        self._last_emitted_end = 0.0

    def _clear_pending(self) -> None:
        """只清空尚未落盘的窗口，保留已落盘前缀用于累计响应去重。"""
        self._text = ""
        self._started_at = None
        self._segment_start = 0.0


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
                # compression 用默认值 'deflate'：7/20-7/22 实测 FunASR C++ 服务端虽不解压
                # 但能正常处理音频（配置信息用默认值），compression=None 反而会导致消息帧异常
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

    @staticmethod
    def protocol_mode_for(task_type: str) -> str:
        """把业务任务类型翻译成 FunASR 真正认识的协议模式。"""
        modes = {
            "realtime": "online",
            "offline": "offline",
        }
        try:
            return modes[task_type]
        except KeyError as exc:
            raise ValueError(f"不支持的 ASR 任务类型: {task_type}") from exc

    def build_start_message(self, task_type: str) -> dict:
        """生成一条可测试的握手消息，避免协议选择散落在发送循环里。"""
        try:
            hotwords = get_hotwords_cached()
        except Exception as exc:
            # 行业知识文件损坏不能阻断整场转写；降级为空热词并保留告警，
            # 后续纠错器仍会使用手工维护的标准词典。
            logger.warning("加载 ASR 行业热词失败，本次按无热词模式继续: %s", exc)
            hotwords = ""
        return {
            "mode": self.protocol_mode_for(task_type),
            "chunk_size": [5, 10, 5],
            "chunk_interval": 10,
            "encoder_chunk_look_back": 4,
            "decoder_chunk_look_back": 0,
            "audio_fs": settings.ASR_SAMPLE_RATE,
            "wav_name": str(self._session_id),
            "wav_format": "pcm",
            "is_speaking": True,
            "hotwords": hotwords,
            "itn": True,
        }

    async def transcribe(
        self,
        session_id: int,
        pcm_frames: AsyncGenerator[bytes, None],
        *,
        task_type: str = "offline",
    ) -> AsyncGenerator[dict, None]:
        """
        实时转写 PCM 流

        Args:
            session_id: 直播场次 ID
            pcm_frames: PCM s16le 帧异步生成器
            task_type: realtime 表示直播初稿，offline 表示下播最终稿

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

        async for result in self._transcribe_pcm(pcm_frames, task_type=task_type):
            yield result

    async def _realtime_transcribe(
        self, pcm_frames: AsyncGenerator[bytes, None]
    ) -> AsyncGenerator[dict, None]:
        """兼容旧调用：历史代码没有任务类型时按离线最终稿处理。"""
        async for result in self._transcribe_pcm(pcm_frames, task_type="offline"):
            yield result

    async def _transcribe_pcm(
        self,
        pcm_frames: AsyncGenerator[bytes, None],
        *,
        task_type: str,
    ) -> AsyncGenerator[dict, None]:
        """按直播状态选择协议，消费真实 PCM 音频。"""
        protocol_mode = self.protocol_mode_for(task_type)
        result_queue: asyncio.Queue = asyncio.Queue()
        receiver_task = None
        draft_buffer = RealtimeDraftBuffer()

        async def receive_results():
            try:
                async for response in self._ws:
                    if isinstance(response, bytes):
                        continue
                    await result_queue.put(json.loads(response))
            except websockets.ConnectionClosed as exc:
                # 接收协程不能静默退出，否则发送方可能把只识别一半的分片误记为完成。
                await result_queue.put({"__connection_error__": str(exc)})

        def raise_if_connection_error(data: dict) -> None:
            if "__connection_error__" in data:
                raise RuntimeError("FunASR 连接中断，本分片将从断点重试")

        def normalize_result(data: dict, elapsed_seconds: float) -> Optional[dict]:
            text = str(data.get("text") or "").strip()
            mode = data.get("mode")
            if not text:
                return None
            if protocol_mode == "offline" and mode in {"online", "2pass-online"}:
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

            result = {
                "text": text,
                "segment_start": start,
                "segment_end": max(start, end),
                "is_final": bool(
                    data.get(
                        "is_final",
                        protocol_mode == "offline" or mode in {"offline", "2pass-offline"},
                    )
                ),
            }
            if protocol_mode == "online":
                return draft_buffer.push(result, mode, elapsed_seconds)
            return result

        try:
            await self._ws.send(json.dumps({
                # 直播中发 online，FunASR 会持续返回初稿；下播后发 offline，
                # 让完整音频经过 VAD、标点和离线模型生成最终稿。
                **self.build_start_message(task_type),
            }))
            # ⚠️ 延迟：确保 FunASR C++ 服务端处理完 JSON 配置消息，
            # 再开始发送 PCM 二进制帧，避免第一条消息被当作二进制 parse error
            await asyncio.sleep(0.5)
            receiver_task = asyncio.create_task(receive_results())

            frame_count = 0
            async for frame in pcm_frames:
                frame_count += 1
                await self._ws.send(frame)
                # 在线模式必须跟真实讲话速度同步发送，否则模型会把几十秒音频瞬间
                # 塞进缓冲区；离线模式无需等真实时间，只做很短的让步避免饿死事件循环。
                await asyncio.sleep(self.frame_interval_for(protocol_mode))

                while not result_queue.empty():
                    data = result_queue.get_nowait()
                    raise_if_connection_error(data)
                    result = normalize_result(data, frame_count * 0.06)
                    if result:
                        yield result

            await self._ws.send(json.dumps({"is_speaking": False}))
            # 没有任何 PCM 帧说明 ffmpeg 实际没读到音频。它不是“整段安静”，
            # 而是流地址过期、回放不存在或音轨读取失败，必须让分片进入重试，
            # 不能误标为已完成后把几十个空分片全部跑一遍。
            if frame_count == 0:
                raise RuntimeError("真实流未输出任何音频帧，请刷新流地址后从断点重试")
            # 流结束后，离线精修结果可能稍晚到达。
            while True:
                try:
                    result_timeout = (
                        settings.ASR_ONLINE_RESULT_TIMEOUT_SECONDS
                        if protocol_mode == "online"
                        else 15
                    )
                    data = await asyncio.wait_for(result_queue.get(), timeout=result_timeout)
                except asyncio.TimeoutError:
                    if receiver_task.done() and not self.connected:
                        raise RuntimeError("FunASR 连接提前结束，本分片将从断点重试")
                    if protocol_mode == "online":
                        buffered_result = draft_buffer.flush(frame_count * 0.06)
                        if buffered_result:
                            yield buffered_result
                    break
                raise_if_connection_error(data)
                result = normalize_result(data, frame_count * 0.06)
                if result:
                    yield result
                if data.get("is_final"):
                    if protocol_mode == "online":
                        buffered_result = draft_buffer.flush(frame_count * 0.06)
                        if buffered_result:
                            yield buffered_result
                    break
        except websockets.ConnectionClosed as exc:
            logger.warning("FunASR 连接断开，本分片将从断点重试")
            raise RuntimeError("FunASR 连接中断，本分片将从断点重试") from exc
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
    @staticmethod
    def frame_interval_for(protocol_mode: str) -> float:
        """在线初稿略快于实时追赶缓存，离线终稿只做事件循环让步。"""
        return (
            settings.ASR_ONLINE_FRAME_INTERVAL_SECONDS
            if protocol_mode == "online"
            else 0.001
        )
