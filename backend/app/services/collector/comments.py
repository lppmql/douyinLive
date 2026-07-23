"""
评论采集和持久化 — 从 manual_collect.py 提取

负责：评论页抓取、评论入库（增量/全量替换）、DOM 文本兜底解析
"""
import asyncio
import re
from datetime import datetime
from typing import Optional

from playwright.async_api import BrowserContext
from sqlalchemy.orm import Session

from app.core.logger import logger
from app.models.comments import Comment
from app.models.live_sessions import LiveSession
from app.services.collector.utils import (
    _comment_belongs_to_session,
    _comment_identity,
    _parse_comment_time,
)

# 企业后台评论页地址
from app.services.collector.constants import COMMENT_URL


def _first_comment_user_value(sources: list[dict], *keys: str) -> object | None:
    """从评论本身或嵌套用户对象中取第一个真实非空字段。"""
    for source in sources:
        for key in keys:
            value = source.get(key)
            if value not in (None, "", [], {}):
                return value
    return None


def _normalize_avatar_url(value: object | None) -> str | None:
    """兼容字符串、URL 列表和抖音常见头像对象，只保留真实 HTTPS 地址。"""
    if isinstance(value, dict):
        value = (
            value.get("urlList")
            or value.get("url_list")
            or value.get("urls")
            or value.get("url")
        )
    if isinstance(value, list):
        value = next((item for item in value if isinstance(item, str) and item.strip()), None)
    if not isinstance(value, str):
        return None
    url = value.strip()
    return url[:1000] if url.startswith("https://") else None


def _parse_comment_user_profile(item: dict) -> dict[str, str | None]:
    """提取评论用户公开资料；sec_uid 只用于去重，绝不冒充公开抖音号。"""
    nested_sources = [
        value
        for value in (item.get("user"), item.get("author"), item.get("userInfo"), item.get("user_info"))
        if isinstance(value, dict)
    ]
    sources = [item, *nested_sources]
    nickname = _first_comment_user_value(sources, "user_nickname", "nickname", "nickName", "displayName")
    avatar = _first_comment_user_value(
        sources,
        "user_avatar_url",
        "avatarUrl",
        "avatar_url",
        "avatarThumb",
        "avatar_thumb",
        "avatar",
    )
    douyin_id = _first_comment_user_value(
        sources,
        "user_douyin_id",
        "douyinId",
        "douyin_id",
        "uniqueId",
        "unique_id",
        "shortId",
        "short_id",
    )
    return {
        "user_nickname": str(nickname).strip()[:100] if nickname not in (None, "") else None,
        "user_avatar_url": _normalize_avatar_url(avatar),
        "user_douyin_id": str(douyin_id).strip()[:100] if douyin_id not in (None, "") else None,
    }


async def _scrape_comments(context: BrowserContext, room_id: str) -> list:
    """访问评论页，采集评论数据"""
    url = f"{COMMENT_URL}?roomId={room_id}&fullscreen=0"
    page = await context.new_page()
    captured_api = []
    response_tasks = []

    async def on_response(resp):
        try:
            ct = resp.headers.get("content-type", "")
            if "json" in ct:
                d = await asyncio.wait_for(resp.json(), timeout=3)
                captured_api.append(d)
        except Exception:
            pass

    page.on("response", lambda r: response_tasks.append(asyncio.create_task(on_response(r))))

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(6)
        # response 回调是异步任务，关闭页面前留出时间让评论 JSON 完整落入缓存。
        await asyncio.sleep(1)
        if response_tasks:
            await asyncio.gather(*response_tasks, return_exceptions=True)
    except Exception:
        pass
    finally:
        await page.close()

    comments = []
    for data in captured_api:
        if not isinstance(data, dict):
            continue
        inner = data.get("data", {}) or {}
        if isinstance(inner, dict) and isinstance(inner.get("data"), dict):
            inner = inner["data"]

        comment_list = None
        if isinstance(inner, list):
            comment_list = inner
        elif isinstance(inner, dict):
            comment_list = inner.get("list") or inner.get("comments") or inner.get("rows")

        if comment_list and isinstance(comment_list, list):
            for c in comment_list:
                if not isinstance(c, dict):
                    continue
                profile = _parse_comment_user_profile(c)
                content = c.get("comment_content") or c.get("content") or ""
                if not content:
                    continue
                comments.append({
                    **profile,
                    "user_sec_uid": c.get("user_sec_uid") or c.get("secUId") or c.get("sec_uid"),
                    "webcast_uid": c.get("webcast_uid") or c.get("webcastUid"),
                    "comment_content": content,
                    "comment_time": _parse_comment_time(c.get("comment_time") or c.get("createTime")),
                })

    return comments


def _save_comments(db: Session, session_id: int, comments: list) -> int:
    """保存评论数据（增量模式，按标识去重）。"""
    session = db.get(LiveSession, session_id)
    existing_by_identity = {
        _comment_identity(row.user_nickname, row.comment_content or "", row.comment_time, row.user_sec_uid): row
        for row in db.query(Comment).filter(Comment.session_id == session_id).all()
    }
    seen_pairs = set()
    count = 0
    profile_updated = False
    for c in comments:
        content = c.get("comment_content", "").strip()
        comment_time = c.get("comment_time")
        if not content:
            continue
        if session and not _comment_belongs_to_session(
            comment_time, session.live_start_time, session.live_end_time
        ):
            logger.warning(
                "拒绝串场评论: session_id=%s comment_time=%s live_range=%s~%s",
                session_id,
                comment_time,
                session.live_start_time,
                session.live_end_time,
            )
            continue

        nickname = c.get("user_nickname", "未知")
        pair = _comment_identity(nickname, content, comment_time, c.get("user_sec_uid"))
        existing = existing_by_identity.get(pair)
        if existing:
            # 同一条评论再次抓到更完整用户资料时只补空字段，不覆盖已保存的真实值。
            for field in ("user_avatar_url", "user_douyin_id", "user_sec_uid", "webcast_uid"):
                value = c.get(field)
                if value and not getattr(existing, field):
                    setattr(existing, field, value)
                    profile_updated = True
            continue
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)

        if content:
            comment = Comment(
                session_id=session_id,
                user_nickname=nickname,
                user_avatar_url=c.get("user_avatar_url"),
                user_douyin_id=c.get("user_douyin_id"),
                user_sec_uid=c.get("user_sec_uid"),
                webcast_uid=c.get("webcast_uid"),
                comment_content=content,
                comment_time=comment_time or datetime.utcnow(),
            )
            db.add(comment)
            count += 1
    if count or profile_updated:
        db.commit()
    return count


def _replace_session_comments(db: Session, session_id: int, comments: list) -> int:
    """用平台完整评论快照替换旧的 DOM 残缺结果，并继承人工分析字段。"""
    old_rows = db.query(Comment).filter(Comment.session_id == session_id).all()
    session = db.get(LiveSession, session_id)
    annotations = {}
    for row in old_rows:
        key = ((row.user_nickname or "").strip(), (row.comment_content or "").strip())
        annotations.setdefault(
            key,
            (
                row.is_high_intent,
                row.sentiment,
                row.keywords,
                row.user_avatar_url,
                row.user_douyin_id,
                row.user_sec_uid,
                row.webcast_uid,
            ),
        )

    db.query(Comment).filter(Comment.session_id == session_id).delete(synchronize_session=False)
    seen = set()
    for item in comments:
        nickname = str(item.get("user_nickname") or "未知").strip()
        content = str(item.get("comment_content") or "").strip()
        comment_time = item.get("comment_time")
        if session and not _comment_belongs_to_session(
            comment_time, session.live_start_time, session.live_end_time
        ):
            continue
        identity = _comment_identity(nickname, content, comment_time, item.get("user_sec_uid"))
        if not content or identity in seen:
            continue
        seen.add(identity)
        annotation = annotations.get((nickname, content), (0, None, None, None, None, None, None))
        db.add(Comment(
            session_id=session_id,
            user_nickname=nickname,
            user_avatar_url=item.get("user_avatar_url") or annotation[3],
            user_douyin_id=item.get("user_douyin_id") or annotation[4],
            user_sec_uid=item.get("user_sec_uid") or annotation[5],
            webcast_uid=item.get("webcast_uid") or annotation[6],
            comment_content=content,
            comment_time=comment_time or datetime.utcnow(),
            is_high_intent=annotation[0] or 0,
            sentiment=annotation[1],
            keywords=annotation[2],
        ))
    db.commit()
    return len(seen)


def _parse_comments_from_live_screen_text(
    body_text: str, live_start_time: Optional[datetime]
) -> list[dict]:
    """从大屏页 DOM 文本中降级解析评论（接口不可用时的兜底）。"""
    lines = [line.strip() for line in body_text.split("\n") if line.strip()]
    comments = []
    i = 0
    pattern = re.compile(r"^\((\d+)\)(\d{2}:\d{2})\s+(.+?)：$")
    while i < len(lines):
        match = pattern.match(lines[i])
        if not match:
            i += 1
            continue

        hhmm = match.group(2)
        nickname = match.group(3).strip()
        content = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if content and not content.startswith("想更方便") and "滑到顶了" not in content:
            comment_time = None
            if live_start_time:
                try:
                    comment_time = live_start_time.replace(
                        hour=int(hhmm.split(":")[0]),
                        minute=int(hhmm.split(":")[1]),
                        second=0,
                        microsecond=0,
                    )
                except Exception:
                    comment_time = None
            comments.append({
                "user_nickname": nickname,
                "comment_content": content,
                "comment_time": comment_time,
            })
        i += 2
    return comments
