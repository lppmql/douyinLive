"""
流地址健康探测工具

两个核心能力：
1. probe_stream_url — 用 ffmpeg 快速探测 m3u8 是否仍可拉流（拉 3 秒就停，不存文件）
2. parse_expiry_from_url — 从抖音 m3u8 URL 的 query string 中提取过期时间戳
"""
from __future__ import annotations

import asyncio
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
) -> dict:
    """
    用 ffmpeg 快速探测 m3u8 流地址是否有效。

    原理：让 ffmpeg 拉几秒流，输出到 /dev/null（不做转码），
    看退出码和 stderr 判断流是否可访问。

    Args:
        stream_url: m3u8 流地址
        headers: 请求头（Referer/User-Agent 等）
        probe_seconds: 探测时长（秒），默认 3 秒
        timeout: 整体超时（秒），默认 12 秒

    Returns:
        {"alive": bool, "error": str|None, "stderr_sample": str|None}
    """
    if not is_valid_stream_url(stream_url):
        return {"alive": False, "error": "流地址格式无效", "stderr_sample": None}

    cmd = _build_ffprobe_command(stream_url, headers, probe_seconds)

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
            return {"alive": True, "error": None, "stderr_sample": "探测超时，流可能仍然可用"}

        stderr_text = stderr.decode(errors="ignore") if stderr else ""

        if process.returncode == 0:
            return {"alive": True, "error": None, "stderr_sample": stderr_text[:200]}

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
                }

        return {
            "alive": False,
            "error": f"ffmpeg 退出码 {process.returncode}",
            "stderr_sample": stderr_text[:200],
        }

    except FileNotFoundError:
        return {"alive": False, "error": "ffmpeg 未安装，无法探测流地址", "stderr_sample": None}
    except Exception as exc:
        return {"alive": False, "error": f"探测异常: {exc}", "stderr_sample": None}


def _build_ffprobe_command(
    stream_url: str,
    headers: Optional[dict],
    probe_seconds: float,
) -> list[str]:
    """构建 ffmpeg 探测命令（拉指定秒数后立即退出，写入 /dev/null）。"""
    cmd = [
        "ffmpeg", "-y",
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

    cmd.extend([
        "-i", stream_url,
        "-f", "null",                    # 输出到空设备（不存文件）
        "-loglevel", "error",
        "/dev/null",
    ])
    return cmd


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
