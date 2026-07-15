"""
ffmpeg pipe 管理器 — 将 m3u8 直播流转为 16kHz PCM 流

使用 asyncio.subprocess 启动 ffmpeg，从 stdout 读取 PCM 数据，
按帧（60ms = 960 samples = 1920 bytes）切分 yield 给调用方。
"""
import asyncio
import json
from typing import AsyncGenerator, Optional

from app.core.config import settings
from app.core.logger import logger


PCM_FRAME_MS = 60           # 每帧 60ms
PCM_SAMPLE_RATE = 16000     # 16kHz
PCM_SAMPLE_BYTES = 2        # s16le = 2 字节/采样
PCM_FRAME_SIZE = int(PCM_SAMPLE_RATE * PCM_FRAME_MS / 1000 * PCM_SAMPLE_BYTES)  # 1920 bytes


class M3u8Pipe:
    """
    ffmpeg pipe 管理器

    用法:
        pipe = M3u8Pipe(m3u8_url, headers)
        async for frame in pipe.read_frames():
            # frame 是 1920 字节的 PCM s16le 数据
            await funasr.send(frame)
    """

    def __init__(
        self,
        m3u8_url: str,
        headers: Optional[dict] = None,
        start_seconds: float = 0,
        duration_seconds: float | None = None,
    ):
        self.m3u8_url = m3u8_url
        self.headers = headers or {}
        self.start_seconds = max(0.0, float(start_seconds or 0))
        self.duration_seconds = (
            max(0.1, float(duration_seconds)) if duration_seconds is not None else None
        )
        self._process: Optional[asyncio.subprocess.Process] = None

    def _build_cmd(self) -> list[str]:
        """构建 ffmpeg 命令"""
        cmd = ["ffmpeg", "-y"]

        # 请求头
        for key, val in self.headers.items():
            if key.lower() in ("referer", "user-agent", "origin"):
                cmd.extend(["-headers", f"{key}: {val}\r\n"])

        if self.start_seconds > 0:
            cmd.extend(["-ss", f"{self.start_seconds:.3f}"])

        cmd.extend([
            "-protocol_whitelist", "https,http,tcp,tls,crypto,file,pipe",
            "-i", self.m3u8_url,
        ])
        if self.duration_seconds is not None:
            cmd.extend(["-t", f"{self.duration_seconds:.3f}"])
        cmd.extend([
            "-vn",                     # 不要视频
            "-threads", "1",           # 限制解码线程，避免与 FunASR 抢占全部 CPU
            "-ac", "1",                # 单声道
            "-ar", str(ASR_SAMPLE_RATE := settings.ASR_SAMPLE_RATE or 16000),  # 16kHz
            "-acodec", "pcm_s16le",    # PCM s16le 编码
            "-f", "s16le",             # 输出格式
            "-loglevel", "error",      # 只显示错误
            "pipe:1",                  # 输出到 stdout
        ])
        return cmd

    async def read_frames(self) -> AsyncGenerator[bytes, None]:
        """
        读取 PCM 帧，每帧 1920 字节（60ms 数据）

        Yields:
            bytes: PCM s16le 帧数据
        """
        cmd = self._build_cmd()
        logger.info(f"ffmpeg 启动: {' '.join(cmd[:6])}...")

        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            while True:
                try:
                    frame = await asyncio.wait_for(
                        self._process.stdout.readexactly(PCM_FRAME_SIZE),
                        timeout=settings.ASR_NO_AUDIO_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "ffmpeg 超过 %ss 未输出音频，结束流读取",
                        settings.ASR_NO_AUDIO_TIMEOUT_SECONDS,
                    )
                    break
                except asyncio.IncompleteReadError as exc:
                    # FFmpeg 正常结束时可能剩下不足 60ms 的尾帧，尾帧不送 ASR。
                    if exc.partial:
                        logger.debug("忽略不足一帧的 PCM 尾数据: %s 字节", len(exc.partial))
                    break
                yield frame

            # 必须先等/停掉 ffmpeg，再读取 stderr。直播 m3u8 进程通常不会主动退出，
            # 反过来读取会一直等待 EOF，导致“无音频超时”形同虚设。
            await self._cleanup()
            stderr = await self._process.stderr.read()
            if stderr:
                logger.warning(f"ffmpeg stderr: {stderr.decode(errors='ignore')[:200]}")

        except asyncio.CancelledError:
            logger.info("ffmpeg pipe 被取消")
            raise
        finally:
            await self._cleanup()

    async def _cleanup(self):
        """清理 ffmpeg 进程"""
        if self._process and self._process.returncode is None:
            try:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=3)
                except asyncio.TimeoutError:
                    logger.warning("ffmpeg 未在 3 秒内退出，执行强制终止")
                    self._process.kill()
                    await self._process.wait()
            except ProcessLookupError:
                pass
        logger.info("ffmpeg pipe 已关闭")

    async def close(self):
        await self._cleanup()
