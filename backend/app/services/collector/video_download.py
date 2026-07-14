"""将已采集的 m3u8 原码流低开销封装为可下载 MP4。"""
import asyncio
from collections.abc import AsyncIterator
from urllib.parse import urlparse

from app.core.logger import logger


video_download_semaphore = asyncio.Semaphore(1)


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
    safe_headers = [
        f"{key}: {value}"
        for key, value in (headers or {}).items()
        if key.lower() in {"referer", "user-agent", "origin"} and value
    ]
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
