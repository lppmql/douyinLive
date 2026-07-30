"""直播音频缓存的文件读取与容量计算测试。"""

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.services.asr.audio_buffer import (
    PCM_BYTES_PER_SECOND,
    LiveAudioBuffer,
    PcmFilePipe,
    prune_audio_buffers,
)
from app.services.asr.m3u8_pipe import PCM_FRAME_SIZE
from workers.asr_worker import AsrWorker


def test_pcm_file_pipe_reads_only_requested_time_range(tmp_path):
    """读取缓存时必须按时间范围截取，不能把相邻分片重复送入识别。"""
    frame = b"\x01\x02" * (PCM_FRAME_SIZE // 2)
    audio_path = tmp_path / "session.pcm"
    # 4 帧，每帧 60ms；请求中间 2 帧。
    audio_path.write_bytes(frame * 4)

    pipe = PcmFilePipe(
        audio_path,
        start_seconds=0.06,
        duration_seconds=0.12,
        wait_for_growth=False,
    )

    async def collect_frames():
        return [item async for item in pipe.read_frames()]

    frames = asyncio.run(collect_frames())

    assert frames == [frame, frame]


def test_pcm_storage_rate_matches_16k_mono_s16le():
    """磁盘容量估算必须与 16kHz、单声道、16 位 PCM 一致。"""
    assert PCM_BYTES_PER_SECOND == 32_000
    assert PCM_BYTES_PER_SECOND * 3600 == 115_200_000


def test_pcm_file_pipe_rejects_partially_cached_chunk(tmp_path):
    """缓存只覆盖分片前半段时必须失败重试，不能虚报整个分片已完成。"""
    frame = b"\x01\x02" * (PCM_FRAME_SIZE // 2)
    audio_path = tmp_path / "partial.pcm"
    audio_path.write_bytes(frame)
    pipe = PcmFilePipe(
        audio_path,
        start_seconds=0,
        duration_seconds=0.12,
        wait_for_growth=False,
    )

    async def collect_frames():
        return [item async for item in pipe.read_frames()]

    with pytest.raises(RuntimeError, match="缓存不完整"):
        asyncio.run(collect_frames())


def test_live_buffer_ffmpeg_command_has_hard_size_limit(tmp_path):
    """单场录音必须由 ffmpeg 自身执行硬上限，不能依赖下一场启动时清理。"""
    audio_buffer = LiveAudioBuffer(
        9,
        "https://example.test/live.m3u8",
        {},
        timeline_start_seconds=0,
        buffer_dir=tmp_path,
        max_bytes=123_456,
    )

    command = audio_buffer._build_command()

    assert command[command.index("-fs") + 1] == "123456"


def test_prune_counts_protected_running_file_in_total_capacity(tmp_path):
    """运行中文件不能删除，但必须计入总容量并挤出旧缓存。"""
    protected = tmp_path / "session-1-1.pcm"
    old = tmp_path / "session-2-1.pcm"
    protected.write_bytes(b"1" * 8)
    old.write_bytes(b"2" * 8)

    deleted = prune_audio_buffers(
        tmp_path,
        retention_hours=24,
        max_bytes=10,
        protected_paths={protected},
    )

    assert deleted == 1
    assert protected.exists()
    assert not old.exists()


def test_two_live_buffers_cannot_allocate_same_capacity_concurrently(tmp_path, monkeypatch):
    """两场直播同时启动时，总预留额度也不能突破配置上限。"""
    worker = AsrWorker()
    worker._audio_buffer_dir = tmp_path

    async def fake_start(audio_buffer):
        # 主动让出事件循环，确保没有容量锁时两条协程会撞在一起。
        await asyncio.sleep(0.01)
        audio_buffer._process = SimpleNamespace(returncode=None)

    monkeypatch.setattr(LiveAudioBuffer, "start", fake_start)
    sessions = [
        SimpleNamespace(id=1, live_start_time=datetime.now()),
        SimpleNamespace(id=2, live_start_time=datetime.now()),
    ]

    async def start_both():
        return await asyncio.gather(
            *[
                worker._start_live_audio_buffer(
                    session,
                    "https://example.test/live.m3u8",
                    {},
                )
                for session in sessions
            ]
        )

    buffers = asyncio.run(start_both())
    allocated = sum(item.max_bytes for item in buffers if item is not None)

    assert sum(item is not None for item in buffers) == 1
    assert allocated <= int(settings.ASR_AUDIO_BUFFER_MAX_GB * 1024**3)


def test_buffer_recounts_old_pcm_after_second_prune(tmp_path, monkeypatch):
    """二次清理未删除旧文件时，旧文件仍必须从新直播额度中扣除。"""
    megabyte = 1024**2
    monkeypatch.setattr(settings, "ASR_AUDIO_BUFFER_MAX_GB", 10 / 1024)
    monkeypatch.setattr(settings, "ASR_CHUNK_SECONDS", 1)
    worker = AsrWorker()
    worker._audio_buffer_dir = tmp_path

    running = LiveAudioBuffer(
        1,
        "https://example.test/first.m3u8",
        {},
        timeline_start_seconds=0,
        buffer_dir=tmp_path,
        max_bytes=6 * megabyte,
    )
    running.audio_path.write_bytes(b"1" * megabyte)
    running._process = SimpleNamespace(returncode=None)
    worker._audio_buffers[1] = running
    # 当前实际占用只有 5MB，小于二次清理目标 6MB，因此清理器会合法保留旧文件；
    # 新额度仍要按“运行中预留 6MB + 旧文件 4MB”计算为 0。
    (tmp_path / "session-99-1.pcm").write_bytes(b"2" * (4 * megabyte))

    result = asyncio.run(
        worker._start_live_audio_buffer(
            SimpleNamespace(id=2, live_start_time=datetime.now()),
            "https://example.test/second.m3u8",
            {},
        )
    )

    assert result is None
