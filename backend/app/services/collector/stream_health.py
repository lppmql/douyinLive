"""
流地址健康探测工具

两个核心能力：
1. probe_stream_url — 用 ffmpeg 快速探测 m3u8 是否仍可拉流（拉 3 秒就停，不存文件）
2. parse_expiry_from_url — 从抖音 m3u8 URL 的 query string 中提取过期时间戳
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import parse_qs, urlparse


# ── 流地址格式校验 ─────────────────────────────────────────────

def is_valid_stream_url(url: str) -> bool:
    """检查 URL 是否至少是合法 HTTP(S) 地址。"""
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


# ── ffmpeg 健康探测 ────────────────────────────────────────────

async def probe_stream_url(
    stream_url: str,
    headers: Optional[dict] = None,
    probe_seconds: float = 3.0,
    timeout: float = 12.0,
    start_seconds: float = 0.0,
) -> dict:
    """
    用 ffmpeg 快速探测 m3u8 流地址是否有效。

    原理：让 ffmpeg 从指定起点拉几秒流，输出到 /dev/null（不做转码），
    看退出码和 stderr 判断流是否可访问，同时解析回放真实总时长。

    Args:
        stream_url: m3u8 流地址
        headers: 请求头（Referer/User-Agent 等）
        probe_seconds: 探测时长（秒），默认 3 秒
        timeout: 整体超时（秒），默认 12 秒
        start_seconds: 从回放的第几秒开始探测，默认 0（流开头）。
            分片失败时按分片起点探测，可以区分“地址有效但末尾定位读不到”
            和“地址真正失效”，避免反复刷新同一个坏地址。

    Returns:
        {"alive": bool, "error": str|None, "stderr_sample": str|None,
         "duration_seconds": float|None}  # duration 为 ffmpeg 实测回放总时长
    """
    if not is_valid_stream_url(stream_url):
        return {"alive": False, "error": "流地址格式无效", "stderr_sample": None}

    cmd = _build_ffprobe_command(stream_url, headers, probe_seconds, start_seconds)

    try:
        process = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            ),
            timeout=5.0,
        )
        try:
            _, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            # ffmpeg 超时：流可能在拉但很慢，保守起见判为 alive
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass
            return {
                "alive": True,
                "error": None,
                "stderr_sample": "探测超时，流可能仍然可用",
                "duration_seconds": None,
            }

        stderr_text = stderr.decode(errors="ignore") if stderr else ""
        duration_seconds = _parse_duration_seconds(stderr_text)

        if process.returncode == 0:
            return {
                "alive": True,
                "error": None,
                "stderr_sample": stderr_text[:200],
                "duration_seconds": duration_seconds,
            }

        # 常见的过期/失效错误关键词
        expired_keywords = [
            "403 Forbidden",
            "404 Not Found",
            "410 Gone",
            "HTTP error 403",
            "HTTP error 404",
            "HTTP error 410",
            "Server returned 4",
            "Server returned 5",
            "Connection refused",
            "No route to host",
            "Name or service not known",
            "Invalid data found when processing input",
        ]
        for keyword in expired_keywords:
            if keyword.lower() in stderr_text.lower():
                return {
                    "alive": False,
                    "error": f"流地址已失效（{keyword.strip()}）",
                    "stderr_sample": stderr_text[:200],
                    "duration_seconds": duration_seconds,
                }

        return {
            "alive": False,
            "error": f"ffmpeg 退出码 {process.returncode}",
            "stderr_sample": stderr_text[:200],
            "duration_seconds": duration_seconds,
        }

    except FileNotFoundError:
        return {
            "alive": False,
            "error": "ffmpeg 未安装，无法探测流地址",
            "stderr_sample": None,
            "duration_seconds": None,
        }
    except Exception as exc:
        return {
            "alive": False,
            "error": f"探测异常: {exc}",
            "stderr_sample": None,
            "duration_seconds": None,
        }


def _build_ffprobe_command(
    stream_url: str,
    headers: Optional[dict],
    probe_seconds: float,
    start_seconds: float = 0.0,
) -> list[str]:
    """构建 ffmpeg 探测命令（从指定起点拉指定秒数，写入 /dev/null）。"""
    cmd = [
        "ffmpeg", "-y",
        "-hide_banner",
        "-t", f"{probe_seconds:.1f}",
        "-rw_timeout", "10000000",       # 10 秒连接超时
        "-protocol_whitelist", "https,http,tcp,tls,crypto",
    ]
    if headers:
        safe_headers = []
        for key, val in headers.items():
            if key.lower() in ("referer", "user-agent", "origin"):
                safe_headers.append(f"{key}: {val}")
        if safe_headers:
            cmd.extend(["-headers", "\r\n".join(safe_headers) + "\r\n"])

    if start_seconds > 0:
        # 与 ASR 分片拉流一致：在 -i 前做快速定位，探测该时间点是否还能读到音频。
        cmd.extend(["-ss", f"{float(start_seconds):.3f}"])

    cmd.extend([
        "-i", stream_url,
        "-f", "null",                    # 输出到空设备（不存文件）
        # info 级别才能让 ffmpeg 打印 Duration，用于解析回放真实总时长；
        # -hide_banner 已控制输出体积，超时机制防止异常流拖长探测。
        "-loglevel", "info",
        "/dev/null",
    ])
    return cmd


# ffmpeg 输出的 Duration 行示例：
# Duration: 00:48:03.61, start: 0.049000, bitrate: 0 kb/s
_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def _parse_duration_seconds(stderr_text: str) -> Optional[float]:
    """从 ffmpeg stderr 解析回放总时长（秒）；解析失败返回 None。"""
    match = _DURATION_RE.search(stderr_text or "")
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    try:
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except ValueError:
        return None


# ── 过期时间解析 ───────────────────────────────────────────────

def parse_expiry_from_url(url: str) -> Optional[datetime]:
    """
    从 m3u8 URL 中解析过期时间戳。

    抖音 CDN 的 m3u8 地址通常在 query string 中带有过期参数：
    - expire=1712345678（Unix 时间戳，秒）
    - deadline=1712345678
    - t=1712345678

    Returns:
        datetime（UTC）或 None（解析失败/URL 不含过期参数）
    """
    if not url:
        return None

    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        # 尝试常见的过期参数名
        for key in ("expire", "deadline", "t", "expires", "valid_until"):
            values = params.get(key)
            if values:
                ts_str = values[0]
                try:
                    ts = int(ts_str)
                except (ValueError, TypeError):
                    # 可能是毫秒级时间戳
                    try:
                        ts = int(ts_str) / 1000
                    except (ValueError, TypeError):
                        continue

                # 合理性检查：时间戳应该在 2020-2100 年之间
                if 1577836800 < ts < 4102444800:  # 2020-01-01 ~ 2100-01-01
                    return datetime.fromtimestamp(ts, tz=timezone.utc)

        # 部分 CDN 直接用 ISO 格式字符串
        for key in ("expires_at", "valid_until_iso"):
            values = params.get(key)
            if values:
                try:
                    return datetime.fromisoformat(values[0].replace(" ", "T"))
                except ValueError:
                    continue

    except Exception:
        pass

    return None


def check_stream_freshness(url: str, warn_threshold_seconds: int = 600) -> dict:
    """
    检查流地址的剩余有效期。

    Returns:
        {"expires_at": datetime|None, "seconds_remaining": int|None, "status": "fresh"|"expiring_soon"|"expired"|"unknown"}
    """
    expires_at = parse_expiry_from_url(url)

    if expires_at is None:
        return {"expires_at": None, "seconds_remaining": None, "status": "unknown"}

    now = datetime.now(timezone.utc)
    remaining = int((expires_at - now).total_seconds())

    if remaining <= 0:
        return {"expires_at": expires_at, "seconds_remaining": remaining, "status": "expired"}
    if remaining <= warn_threshold_seconds:
        return {"expires_at": expires_at, "seconds_remaining": remaining, "status": "expiring_soon"}
    return {"expires_at": expires_at, "seconds_remaining": remaining, "status": "fresh"}
