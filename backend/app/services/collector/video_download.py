"""将已采集的 m3u8 原码流低开销封装为可下载 MP4。"""
import asyncio
import subprocess
from collections.abc import AsyncIterator
from functools import lru_cache
from urllib.parse import urlparse

from app.core.logger import logger


video_download_semaphore = asyncio.Semaphore(1)
browser_playback_lock = asyncio.Lock()
active_browser_playback_process: asyncio.subprocess.Process | None = None


def _safe_ffmpeg_headers(headers: dict | None) -> list[str]:
    return [
        f"{key}: {value}"
        for key, value in (headers or {}).items()
        if key.lower() in {"referer", "user-agent", "origin"} and value
    ]


def build_video_download_command(stream_url: str, headers: dict | None = None) -> list[str]:
    """构建仅封装、不重新编码的 ffmpeg 命令。"""
    if urlparse(stream_url).scheme not in {"http", "https"}:
        raise ValueError("直播流地址不是可下载的 HTTP/HTTPS 地址")

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-rw_timeout",
        "15000000",
        "-protocol_whitelist",
        "https,http,tcp,tls,crypto",
    ]
    safe_headers = _safe_ffmpeg_headers(headers)
    if safe_headers:
        command.extend(["-headers", "\r\n".join(safe_headers) + "\r\n"])
    command.extend([
        "-i",
        stream_url,
        "-map",
        "0:v?",
        "-map",
        "0:a?",
        "-c",
        "copy",
        "-bsf:a",
        "aac_adtstoasc",
        "-movflags",
        "frag_keyframe+empty_moov+default_base_moof",
        "-f",
        "mp4",
        "pipe:1",
    ])
    return command


@lru_cache(maxsize=1)
def select_browser_h264_encoder() -> str:
    """优先使用 macOS 硬件编码，其他环境回退为单线程软件编码。"""
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        check=False,
    )
    return "h264_videotoolbox" if "h264_videotoolbox" in result.stdout else "libx264"


def build_browser_playback_command(
    stream_url: str,
    headers: dict | None = None,
    start_seconds: float = 0,
    encoder: str | None = None,
) -> list[str]:
    """把 H.265 回放低资源转换为浏览器可播放的 H.264 fragmented MP4。"""
    if urlparse(stream_url).scheme not in {"http", "https"}:
        raise ValueError("直播流地址不是可播放的 HTTP/HTTPS 地址")

    selected_encoder = encoder or select_browser_h264_encoder()
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-rw_timeout",
        "15000000",
        "-protocol_whitelist",
        "https,http,tcp,tls,crypto",
    ]
    safe_headers = _safe_ffmpeg_headers(headers)
    if safe_headers:
        command.extend(["-headers", "\r\n".join(safe_headers) + "\r\n"])
    if start_seconds > 0:
        command.extend(["-ss", f"{start_seconds:.3f}"])
    # M 芯片硬件编码器效率极高，全速转码让前端获得充足缓冲，播放更流畅。
    command.extend([
        "-i",
        stream_url,
        "-map",
        "0:v:0?",
        "-map",
        "0:a:0?",
        "-c:v",
        selected_encoder,
    ])
    if selected_encoder == "h264_videotoolbox":
        command.extend(["-b:v", "2500k", "-maxrate", "3500k", "-bufsize", "5000k", "-realtime", "true"])
    else:
        command.extend(["-preset", "veryfast", "-crf", "25", "-threads", "1"])
    command.extend([
        "-pix_fmt",
        "yuv420p",
        "-tag:v",
        "avc1",
        "-g",
        "50",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "frag_keyframe+empty_moov+default_base_moof",
        "-frag_duration",
        "1000000",
        "-f",
        "mp4",
        "pipe:1",
    ])
    return command


async def stream_video_as_mp4(stream_url: str, headers: dict | None = None) -> AsyncIterator[bytes]:
    """逐块输出 MP4，浏览器可直接写入用户选择的本地文件。"""
    command = build_video_download_command(stream_url, headers)
    async with video_download_semaphore:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            while True:
                chunk = await process.stdout.read(256 * 1024)
                if not chunk:
                    break
                yield chunk
            return_code = await process.wait()
            stderr = (await process.stderr.read()).decode(errors="ignore").strip()
            if return_code:
                logger.warning("直播视频封装失败 code=%s: %s", return_code, stderr[:500])
                raise RuntimeError("直播流已失效或视频封装失败，请重新采集流地址后重试")
        finally:
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=3)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()


async def stream_browser_playback(
    stream_url: str,
    headers: dict | None = None,
    start_seconds: float = 0,
) -> AsyncIterator[bytes]:
    """单路、限速输出 H.264 兼容流，最新播放请求会接管旧进程。"""
    global active_browser_playback_process

    encoder = await asyncio.to_thread(select_browser_h264_encoder)
    command = build_browser_playback_command(stream_url, headers, start_seconds, encoder)
    async with browser_playback_lock:
        previous_process = active_browser_playback_process
        if previous_process and previous_process.returncode is None:
            previous_process.terminate()
            try:
                await asyncio.wait_for(previous_process.wait(), timeout=3)
            except asyncio.TimeoutError:
                previous_process.kill()
                await previous_process.wait()
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        active_browser_playback_process = process
    try:
        while True:
            chunk = await process.stdout.read(256 * 1024)
            if not chunk:
                break
            yield chunk
        return_code = await process.wait()
        stderr = (await process.stderr.read()).decode(errors="ignore").strip()
        async with browser_playback_lock:
            is_current_process = active_browser_playback_process is process
        if return_code and is_current_process:
            logger.warning("浏览器兼容回放失败 code=%s: %s", return_code, stderr[:500])
            raise RuntimeError("回放流已失效或兼容转换失败，请重新采集后重试")
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        async with browser_playback_lock:
            if active_browser_playback_process is process:
                active_browser_playback_process = None
