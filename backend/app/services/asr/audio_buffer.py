"""直播 PCM 音频缓存。

直播音频先由独立 ffmpeg 进程连续写入本地 PCM 文件，转写任务再按时间范围读取。
这样即使 FunASR 临时处理已结束直播，正在直播的声音也不会因为排队而丢失。
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import AsyncGenerator

from app.core.config import settings
from app.core.logger import logger
from app.services.asr.m3u8_pipe import PCM_FRAME_SIZE, PCM_SAMPLE_BYTES, PCM_SAMPLE_RATE


PCM_BYTES_PER_SECOND = PCM_SAMPLE_RATE * PCM_SAMPLE_BYTES
PCM_FRAME_SECONDS = PCM_FRAME_SIZE / PCM_BYTES_PER_SECOND


class PcmFilePipe:
    """把持续增长的 PCM 文件按指定时间范围转换为 ASR 帧。"""

    def __init__(
        self,
        audio_path: Path,
        *,
        start_seconds: float = 0,
        duration_seconds: float | None = None,
        wait_for_growth: bool = True,
    ) -> None:
        self.audio_path = Path(audio_path)
        self.start_seconds = max(0.0, float(start_seconds or 0))
        self.duration_seconds = (
            max(PCM_FRAME_SECONDS, float(duration_seconds))
            if duration_seconds is not None
            else None
        )
        self.wait_for_growth = wait_for_growth
        self.last_error_message = ""
        self._closed = False

    async def read_frames(self) -> AsyncGenerator[bytes, None]:
        """逐帧读取请求区间；直播缓存尚未写到目标位置时短暂等待。"""
        start_byte = int(self.start_seconds * PCM_BYTES_PER_SECOND)
        # 保证始终从完整的 60ms 帧边界开始读取。
        start_byte -= start_byte % PCM_FRAME_SIZE
        requested_bytes = (
            int(self.duration_seconds * PCM_BYTES_PER_SECOND)
            if self.duration_seconds is not None
            else None
        )
        if requested_bytes is not None:
            requested_bytes -= requested_bytes % PCM_FRAME_SIZE

        consumed = 0
        idle_seconds = 0.0
        poll_interval = 0.1
        audio_file = None
        try:
            while not self._closed:
                if requested_bytes is not None and consumed >= requested_bytes:
                    break

                try:
                    if audio_file is None:
                        audio_file = self.audio_path.open("rb")
                        audio_file.seek(start_byte)
                    audio_file.seek(start_byte + consumed)
                    frame = audio_file.read(PCM_FRAME_SIZE)
                except FileNotFoundError:
                    frame = b""

                if len(frame) == PCM_FRAME_SIZE:
                    consumed += PCM_FRAME_SIZE
                    idle_seconds = 0.0
                    yield frame
                    continue

                if not self.wait_for_growth:
                    break

                idle_seconds += poll_interval
                if idle_seconds >= settings.ASR_NO_AUDIO_TIMEOUT_SECONDS:
                    self.last_error_message = "直播音频缓存等待超时"
                    break
                await asyncio.sleep(poll_interval)
        finally:
            if audio_file is not None:
                audio_file.close()
        if requested_bytes is not None and consumed < requested_bytes and not self._closed:
            covered_seconds = consumed / PCM_BYTES_PER_SECOND
            self.last_error_message = (
                f"直播音频缓存不完整：请求 {self.duration_seconds:.1f} 秒，"
                f"实际仅读取 {covered_seconds:.1f} 秒"
            )
            raise RuntimeError(self.last_error_message)

    async def close(self) -> None:
        """停止等待；文件由缓存管理器统一维护，不在这里删除。"""
        self._closed = True


class LiveAudioBuffer:
    """用独立 ffmpeg 连续记录一场直播，并提供绝对时间轴读取。"""

    def __init__(
        self,
        session_id: int,
        m3u8_url: str,
        headers: dict[str, str] | None,
        *,
        timeline_start_seconds: float,
        buffer_dir: Path,
        max_bytes: int,
    ) -> None:
        self.session_id = session_id
        self.m3u8_url = m3u8_url
        self.headers = headers or {}
        self.timeline_start_seconds = max(0.0, float(timeline_start_seconds))
        self.buffer_dir = Path(buffer_dir)
        self.max_bytes = max(PCM_FRAME_SIZE, int(max_bytes))
        self.audio_path = self.buffer_dir / f"session-{session_id}-{int(time.time())}.pcm"
        self._process: asyncio.subprocess.Process | None = None

    def _build_command(self) -> list[str]:
        """构建带硬容量上限的 ffmpeg 命令。"""
        command = ["ffmpeg", "-y"]
        for key, value in self.headers.items():
            if key.lower() in {"referer", "user-agent", "origin"}:
                command.extend(["-headers", f"{key}: {value}\r\n"])
        command.extend(
            [
                "-protocol_whitelist",
                "https,http,tcp,tls,crypto,file,pipe",
                "-i",
                self.m3u8_url,
                "-vn",
                "-threads",
                "1",
                "-ac",
                "1",
                "-ar",
                str(settings.ASR_SAMPLE_RATE or PCM_SAMPLE_RATE),
                "-acodec",
                "pcm_s16le",
                "-f",
                "s16le",
                "-loglevel",
                "error",
                "-fs",
                str(self.max_bytes),
                str(self.audio_path),
            ]
        )
        return command

    async def start(self) -> None:
        """启动真实直播音频记录；URL 和请求头绝不写入日志。"""
        self.buffer_dir.mkdir(parents=True, exist_ok=True)
        command = self._build_command()
        self._process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        logger.info(
            "场次 %s 直播音频连续缓存已启动，时间轴起点 %.1fs",
            self.session_id,
            self.timeline_start_seconds,
        )

    def pipe_for_range(self, start_seconds: float, duration_seconds: float) -> PcmFilePipe:
        """把整场绝对时间换算为缓存文件内的相对时间。"""
        return PcmFilePipe(
            self.audio_path,
            start_seconds=max(0.0, start_seconds - self.timeline_start_seconds),
            duration_seconds=duration_seconds,
            wait_for_growth=self.is_running,
        )

    @property
    def is_running(self) -> bool:
        return bool(self._process and self._process.returncode is None)

    @property
    def available_seconds(self) -> float:
        try:
            return self.audio_path.stat().st_size / PCM_BYTES_PER_SECOND
        except FileNotFoundError:
            return 0.0

    def covers_range(self, start_seconds: float, end_seconds: float) -> bool:
        """缓存已经落盘的区间才可供已结束直播复用。"""
        if start_seconds < self.timeline_start_seconds:
            return False
        return end_seconds <= self.timeline_start_seconds + self.available_seconds

    async def stop(self) -> None:
        """停止记录但保留文件，供刚下播的完整度补齐复用。"""
        if self._process and self._process.returncode is None:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=3)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            except ProcessLookupError:
                pass
        logger.info(
            "场次 %s 直播音频连续缓存已停止，共 %.1f 秒",
            self.session_id,
            self.available_seconds,
        )


def prune_audio_buffers(
    buffer_dir: Path,
    *,
    retention_hours: int,
    max_bytes: int,
    protected_paths: set[Path] | None = None,
) -> int:
    """按保留时间和总容量清理旧缓存，返回删除文件数。"""
    directory = Path(buffer_dir)
    if not directory.exists():
        return 0
    now = time.time()
    protected = {Path(item).resolve() for item in (protected_paths or set())}
    files = sorted(
        (item for item in directory.glob("session-*.pcm") if item.is_file()),
        key=lambda item: item.stat().st_mtime,
    )
    deleted = 0
    retention_seconds = retention_hours * 3600
    for item in list(files):
        if item.resolve() in protected or now - item.stat().st_mtime <= retention_seconds:
            continue
        item.unlink(missing_ok=True)
        files.remove(item)
        deleted += 1

    total_bytes = sum(item.stat().st_size for item in files)
    for item in files:
        if total_bytes <= max_bytes:
            break
        if item.resolve() in protected:
            continue
        size = item.stat().st_size
        item.unlink(missing_ok=True)
        total_bytes -= size
        deleted += 1
    return deleted
