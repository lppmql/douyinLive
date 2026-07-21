"""
采集通用工具函数 — 从 manual_collect.py 提取

包含：数值解析、时间解析、URL 解析、Cookie 读取、去重标识、评论时间校验
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs


# ==================== 数值解析 ====================


def _safe_int(val) -> Optional[int]:
    """安全转为整数，兼容逗号分隔和浮点数字符串。"""
    if val is None:
        return None
    try:
        return int(float(str(val).replace(",", "")))
    except (ValueError, TypeError):
        return None


def _safe_float(val) -> Optional[float]:
    """安全转为浮点数，兼容逗号和百分号。"""
    if val is None:
        return None
    try:
        return float(str(val).replace(",", "").replace("%", ""))
    except (ValueError, TypeError):
        return None


def _extract_next_number(lines: list[str], label: str) -> Optional[int]:
    """从标签后的下一项中提取整数。"""
    try:
        idx = lines.index(label)
    except ValueError:
        return None

    for item in lines[idx + 1: idx + 6]:
        cleaned = item.replace(",", "").replace("%", "").strip()
        if cleaned.isdigit():
            return int(cleaned)
    return None


# ==================== 时间解析 ====================


def _parse_dt(val: Optional[str]) -> Optional[datetime]:
    """解析 YYYY-MM-DD HH:MM:SS 格式的时间字符串。"""
    if not val:
        return None
    try:
        return datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _parse_epoch_dt(value) -> Optional[datetime]:
    """转换 Unix 秒/毫秒时间戳为 datetime。"""
    if value in (None, "", 0, "0"):
        return None
    try:
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp)
    except (TypeError, ValueError, OverflowError):
        return None


def _parse_comment_time(value) -> Optional[datetime]:
    """兼容评论接口的 Unix 秒、毫秒和 datetime 字符串。"""
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp)
    if isinstance(value, str) and value:
        return _parse_dt(value) or None
    return None


# ==================== URL 解析 ====================


def _extract_room_id_from_dashboard_url(url: Optional[str]) -> Optional[str]:
    """从大屏页 URL 中提取 room_id 参数。"""
    if not url:
        return None
    try:
        parsed = urlparse(url)
        room_ids = parse_qs(parsed.query).get("room_id") or parse_qs(parsed.query).get("roomId")
        if room_ids:
            return room_ids[0]
    except Exception:
        return None
    return None


# ==================== 历史场次校验 ====================


def _is_expected_history_session(body_text: str, live_start_time: datetime, live_end_time: datetime) -> bool:
    """校验当前详情页是否真的是目标场次，避免历史页面串场写错数据。"""
    if not body_text or not live_start_time or not live_end_time:
        return False

    normalized_text = body_text.replace("：", ":").replace("〜", "~").replace("～", "~")
    for expected in _build_expected_session_markers(live_start_time, live_end_time):
        if expected in normalized_text:
            return True
    return False


def _build_expected_session_markers(start_time: datetime, end_time: datetime) -> list[str]:
    """构造页面上可能出现的场次时间文案。"""
    candidates = set()
    start_variants = _format_session_time_variants(start_time)
    end_variants = _format_session_time_variants(end_time)
    prefixes = ["场次:", "场次：", ""]
    separators = [" ~ ", "~", " - ", "-"]

    for prefix in prefixes:
        for start_variant in start_variants:
            for end_variant in end_variants:
                for separator in separators:
                    candidates.add(f"{prefix}{start_variant}{separator}{end_variant}".strip())

    return sorted(candidates)


def _format_session_time_variants(value: datetime) -> list[str]:
    """兼容大屏页常见时间格式。"""
    base = value.replace(microsecond=0)
    next_day = base + timedelta(days=1)
    return [
        base.strftime("%m-%d %H:%M:%S"),
        base.strftime("%m-%d %H:%M"),
        base.strftime("%Y-%m-%d %H:%M:%S"),
        base.strftime("%Y-%m-%d %H:%M"),
        next_day.strftime("%H:%M:%S"),
        next_day.strftime("%H:%M"),
    ]


# ==================== 通用取值 ====================


def _first_value(data: dict, *keys: str):
    """返回第一个存在且非空的兼容字段值。"""
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


# ==================== Cookie ====================


def _load_storage_cookies(storage_state_path: str) -> dict[str, str]:
    """从 Playwright storage_state 文件中提取 Cookie。"""
    if not storage_state_path:
        return {}
    path = Path(storage_state_path)
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    cookies = {}
    for item in payload.get("cookies", []) or []:
        name = item.get("name")
        value = item.get("value")
        if name and value:
            cookies[name] = value
    return cookies


# ==================== 评论去重和校验 ====================


def _comment_identity(
    nickname: Optional[str],
    content: str,
    comment_time: Optional[datetime],
    user_sec_uid: Optional[str] = None,
) -> tuple[str, str, Optional[datetime]]:
    """按稳定用户、内容和时间去重，不误删不同用户同一秒的相同评论。"""
    normalized_time = comment_time.replace(microsecond=0) if isinstance(comment_time, datetime) else None
    user_identity = str(user_sec_uid or nickname or "未知").strip()
    return (user_identity, content, normalized_time)


def _comment_belongs_to_session(comment_time: Optional[datetime], live_start_time, live_end_time) -> bool:
    """评论时间必须落在本场直播区间内，边界放宽两分钟兼容平台时间误差。"""
    if not comment_time or not live_start_time:
        return True
    tolerance = timedelta(minutes=2)
    if comment_time < live_start_time - tolerance:
        return False
    if live_end_time and comment_time > live_end_time + tolerance:
        return False
    return True


# ==================== 上下文错误检测 ====================


def _is_context_closed_message(value) -> bool:
    """识别采集结果中的 Playwright 浏览器句柄关闭错误。"""
    text = str(value or "").lower()
    return any(marker in text for marker in (
        "target page, context or browser has been closed",
        "browsercontext.new_page",
        "browser.new_context",
        "浏览器进程意外退出",
        "handler is closed",
        "transport closed",
    ))
