"""回放视频下载器：把抖音 m3u8 回放流落盘为本地 MP4。

直播回放源（m3u8）有有效期，且系统只在浏览器播放时临时缓存分片（/tmp），
因此剪辑前必须先下载完整回放到 data/videos/<session_id>/replay.mp4。
下载失败时自动用现有 stream_refresh 服务刷新流地址后重试一次。

注意：本模块是同步实现（subprocess.run），与剪辑管线一致——
采集控制中心的 clip 任务在 to_thread 线程中执行，不使用 asyncio。
"""

from __future__ import annotations

import asyncio
import subprocess
import threading
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, settings
from app.core.logger import logger
from app.models.stream_sources import StreamSource

# 回放下载与剪辑共用同一把锁，避免同时多个 ffmpeg 抢资源
replay_download_lock = threading.Lock()

MIN_REPLAY_BYTES = 1024 * 1024  # 小于 1MB 视为下载不完整


def session_video_dir(session_id: int) -> Path:
    """场次视频目录：data/videos/<session_id>/"""
    return Path(PROJECT_ROOT) / settings.CLIP_STORAGE_DIR / str(session_id)


def replay_path(session_id: int) -> Path:
    return session_video_dir(session_id) / "replay.mp4"


def _safe_ffmpeg_headers(headers: dict | None) -> list[str]:
    return [
        f"{key}: {value}"
        for key, value in (headers or {}).items()
        if key.lower() in {"referer", "user-agent", "origin"} and value
    ]


def build_replay_download_command(
    stream_url: str, headers: dict | None = None, output: str = ""
) -> list[str]:
    """构建回放下载 ffmpeg 命令：流拷贝（不重编码），HLS AAC 转 MP4 兼容。"""
    safe_headers = _safe_ffmpeg_headers(headers)
    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-rw_timeout",
        "15000000",
        "-protocol_whitelist",
        "https,http,tcp,tls,crypto",
    ]
    if safe_headers:
        command.extend(["-headers", "\r\n".join(safe_headers) + "\r\n"])
    command.extend(
        [
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
            "+faststart",
            "-f",
            "mp4",
            output,
        ]
    )
    return command


def _download_replay(stream_url: str, headers: dict | None, output_path: Path) -> None:
    """执行 ffmpeg 下载，超时或失败抛异常由调用方兜底。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = build_replay_download_command(stream_url, headers, str(output_path))
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=settings.CLIP_REPLAY_DOWNLOAD_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise TimeoutError("回放下载超时，流地址可能已失效")
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()[-500:]
        raise RuntimeError(f"回放下载失败 code={result.returncode}: {stderr}")


def _pick_stream_source(db: Session, session_id: int) -> StreamSource | None:
    """挑选可用的回放流源：优先 active，其次 pending，再次 expired（可能仍有效）。"""
    from sqlalchemy import case

    status_rank = case(
        (StreamSource.status == "active", 0),
        (StreamSource.status == "pending", 1),
        (StreamSource.status == "expired", 2),
        else_=3,
    )
    return (
        db.query(StreamSource)
        .filter(
            StreamSource.session_id == session_id, StreamSource.m3u8_url.isnot(None)
        )
        .order_by(status_rank, StreamSource.fetched_at.desc())
        .first()
    )


def ensure_replay_file(db: Session, session_id: int) -> Path:
    """确保场次回放已落盘，返回 replay.mp4 路径；彻底失败抛异常。

    幂等：文件已存在且大于 1MB 直接复用（手动重剪不重复下载）。
    """
    existing = replay_path(session_id)
    if existing.exists() and existing.stat().st_size > MIN_REPLAY_BYTES:
        return existing

    source = _pick_stream_source(db, session_id)
    if not source:
        raise ValueError(
            f"场次 #{session_id} 没有可用的回放流地址（stream_sources 为空）"
        )

    headers = dict(source.headers_json or {})
    with replay_download_lock:
        try:
            logger.info(
                "开始下载回放 session=%s url=%s...", session_id, source.m3u8_url[:80]
            )
            _download_replay(source.m3u8_url, headers, existing)
        except Exception as exc:
            # 流地址可能已过期：用已保存 Cookie 刷新大屏页重新抓取后重试一次
            logger.warning(
                "回放下载失败，尝试刷新流地址后重试 session=%s: %s", session_id, exc
            )
            from app.services.collector.stream_refresh import refresh_session_stream_url

            refreshed = asyncio.run(refresh_session_stream_url(db, session_id))
            if not refreshed.get("success") or not refreshed.get("stream_url"):
                raise RuntimeError(
                    f"回放下载失败且流地址刷新失败（{refreshed.get('error')}），"
                    "该场次可能已无法获取回放"
                ) from exc
            _download_replay(refreshed["stream_url"], headers, existing)

    if not existing.exists() or existing.stat().st_size <= MIN_REPLAY_BYTES:
        raise RuntimeError("回放下载完成但文件不完整（小于 1MB）")
    logger.info(
        "回放就绪 session=%s size=%.1fMB",
        session_id,
        existing.stat().st_size / 1024 / 1024,
    )
    return existing
