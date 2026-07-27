"""FunASR 空音频保护测试。"""

import asyncio
import json

import pytest

from app.services.asr.funasr_client import FunasrClient


class _EmptyWebSocket:
    """只接收配置、不返回结果的最小测试 WebSocket。"""

    def __init__(self):
        self.sent_messages = []

    async def send(self, message):
        self.sent_messages.append(message)

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


async def _empty_pcm_frames():
    """模拟 ffmpeg 没有输出任何真实 PCM 音频帧。"""
    if False:
        yield b""


def test_empty_pcm_stream_is_not_marked_as_success():
    """空流必须失败重试，不能把几十个空分片全部误标为完成。"""
    async def run_scenario():
        client = FunasrClient("ws://test.invalid")
        websocket = _EmptyWebSocket()
        client._ws = websocket

        with pytest.raises(RuntimeError, match="未输出任何音频帧"):
            async for _result in client._realtime_transcribe(_empty_pcm_frames()):
                pass

        assert json.loads(websocket.sent_messages[-1]) == {"is_speaking": False}

    asyncio.run(run_scenario())
