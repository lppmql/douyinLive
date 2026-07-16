"""将已采集的 m3u8 原码流低开销封装为可下载 MP4 或转码为兼容 H.264 回放。"""
import asyncio
import os
import subprocess
import tempfile
from collections.abc import AsyncIterator
from functools import lru_cache
from urllib.parse import urljoin, urlparse

import httpx

from app.core.logger import logger


video_download_semaphore = asyncio.Semaphore(1)
browser_playback_lock = asyncio.Lock()
active_browser_playback_process: asyncio.subprocess.Process | None = None

PLAYBACK_CACHE_DIR = os.path.join(tempfile.gettempdir(), "douyin-live-playback")


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


# ── HLS 分片缓存 ──────────────────────────────────────────────

async def _download_m3u8(url: str, headers: dict | None) -> str:
    """下载 m3u8 索引文件内容。"""
    async with httpx.AsyncClient(http2=True, timeout=30) as client:
        resp = await client.get(url, headers=headers or {})
        resp.raise_for_status()
        return resp.text


def _parse_m3u8_segments(m3u8_content: str, base_url: str) -> list[str]:
    """从 m3u8 文本中解析 ts 分片绝对 URL。"""
    segments: list[str] = []
    for line in m3u8_content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        segments.append(urljoin(base_url, line))
    return segments


def _session_cache_dir(session_id: int) -> str:
    return os.path.join(PLAYBACK_CACHE_DIR, str(session_id), "segments")


def _concat_file_path(session_id: int) -> str:
    return os.path.join(PLAYBACK_CACHE_DIR, str(session_id), "concat.txt")


async def _download_segments_to_cache(
    segment_urls: list[str],
    session_id: int,
    headers: dict | None = None,
) -> str | None:
    """下载所有 ts 分片到本地缓存，返回 concat 文件路径；失败返回 None。"""
    seg_dir = _session_cache_dir(session_id)
    os.makedirs(seg_dir, exist_ok=True)

    safe_headers = {k: v for k, v in (headers or {}).items() if k.lower() in {"referer", "user-agent", "origin"}}

    async with httpx.AsyncClient(http2=True, timeout=30) as client:
        for idx, seg_url in enumerate(segment_urls):
            seg_path = os.path.join(seg_dir, f"{idx:06d}.ts")
            if os.path.exists(seg_path) and os.path.getsize(seg_path) > 0:
                continue  # 已缓存
            try:
                resp = await client.get(seg_url, headers=safe_headers)
                resp.raise_for_status()
                with open(seg_path, "wb") as f:
                    f.write(resp.content)
            except Exception as exc:
                logger.warning("分片下载失败 idx=%d url=%s: %s", idx, seg_url[:80], exc)
                return None  # 任一片失败 → 不使用缓存（回退直连）

    # 写入 concat 文件
    concat_path = _concat_file_path(session_id)
    with open(concat_path, "w") as f:
        for idx in range(len(segment_urls)):
            seg_path = os.path.join(seg_dir, f"{idx:06d}.ts")
            # 用引号包裹路径以兼容空格等特殊字符
            f.write(f"file '{seg_path}'\n")
    return concat_path


async def _ensure_segment_cache(
    m3u8_url: str,
    session_id: int,
    headers: dict | None = None,
) -> str | None:
    """确保分片已缓存，返回 concat 文件路径；任何失败返回 None。"""
    concat_path = _concat_file_path(session_id)
    if os.path.exists(concat_path):
        return concat_path

    try:
        m3u8_content = await _download_m3u8(m3u8_url, headers)
    except Exception as exc:
        logger.warning("m3u8 下载失败: %s", exc)
        return None

    base_url = m3u8_url[: m3u8_url.rfind("/") + 1] if "/" in m3u8_url else m3u8_url
    segments = _parse_m3u8_segments(m3u8_content, base_url)
    if not segments:
        logger.warning("m3u8 中未解析到分片")
        return None

    return await _download_segments_to_cache(segments, session_id, headers)


def build_cached_playback_command(
    session_id: int,
    start_seconds: float = 0,
    encoder: str | None = None,
) -> list[str]:
    """从本地缓存分片构建 ffmpeg 命令。"""
    selected_encoder = encoder or select_browser_h264_encoder()
    concat_file = _concat_file_path(session_id)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
    ]
    if start_seconds > 0:
        command.extend(["-ss", f"{start_seconds:.3f}"])
    command.extend([
        "-i",
        concat_file,
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


def build_browser_playback_command(
    stream_url: str,
    headers: dict | None = None,
    start_seconds: float = 0,
    encoder: str | None = None,
) -> list[str]:
    """把 H.265 回放低资源转换为浏览器可播放的 H.264 fragmented MP4（直连 CDN 模式）。"""
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
    session_id: int = 0,
) -> AsyncIterator[bytes]:
    """输出 H.264 兼容流，优先使用本地缓存，兜底直连 CDN 转码。"""
    global active_browser_playback_process

    encoder = await asyncio.to_thread(select_browser_h264_encoder)
    t0 = asyncio.get_event_loop().time()

    # 优先尝试本地分片缓存
    concat_path = None
    if session_id > 0:
        concat_path = await _ensure_segment_cache(stream_url, session_id, headers)
        if concat_path:
            logger.info("[缓存] 分片缓存就绪 session=%d 耗时=%.1fs", session_id, asyncio.get_event_loop().time() - t0)

    if concat_path:
        command = build_cached_playback_command(session_id, start_seconds, encoder)
        source_label = f"缓存({session_id})"
    else:
        command = build_browser_playback_command(stream_url, headers, start_seconds, encoder)
        source_label = "CDN"

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

    first = True
    try:
        while True:
            chunk = await process.stdout.read(256 * 1024)
            if not chunk:
                break
            if first:
                logger.info(
                    "[播放] 首块到达 source=%s 耗时=%.1fs",
                    source_label,
                    asyncio.get_event_loop().time() - t0,
                )
                first = False
            yield chunk
        return_code = await process.wait()
        stderr = (await process.stderr.read()).decode(errors="ignore").strip()
        logger.info("[播放] 结束 source=%s code=%s 耗时=%.1fs", source_label, return_code, asyncio.get_event_loop().time() - t0)
        async with browser_playback_lock:
            is_current_process = active_browser_playback_process is process
        if return_code and is_current_process:
            logger.warning("浏览器兼容回放失败 code=%s stderr=%s", return_code, stderr[:500])
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
