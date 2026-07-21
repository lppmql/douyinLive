"""
企业主播同步 — 从 manual_collect.py 提取

负责：企业后台员工接口分页读取、主播与场次映射、正在直播场次发现
"""
import asyncio
import json
from typing import Optional

from playwright.async_api import BrowserContext
from sqlalchemy.orm import Session

from app.core.logger import logger
from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.models.scraper_logs import ScraperLog
from app.services.collector.room import _fetch_enterprise_post
from app.services.collector.session import _apply_session_anchor_profile
from app.services.collector.utils import (
    _first_value,
    _is_context_closed_message,
    _parse_epoch_dt,
    _safe_int,
)

# 企业后台地址
from app.services.collector.constants import LIVE_SCREEN_URL, COMMENT_URL
ENTERPRISE_PAGE_SIZE = 100
ENTERPRISE_MAX_PAGES = 200


async def _fetch_enterprise_rows(
    page,
    path: str,
    payload: dict,
    csrf_token: str,
    row_keys: tuple[str, ...],
    max_pages: int = ENTERPRISE_MAX_PAGES,
) -> tuple[list[dict], Optional[dict]]:
    """分页读取企业接口，并兼容不同版本的列表字段。"""
    rows: list[dict] = []
    seen: set[str] = set()
    self_profile = None

    for page_no in range(1, max_pages + 1):
        page_payload = {
            **payload,
            "pageNum": page_no,
            "pageNo": page_no,
            "page": page_no,
            "pageSize": ENTERPRISE_PAGE_SIZE,
            "limit": ENTERPRISE_PAGE_SIZE,
        }
        response = await _fetch_enterprise_post(page, path, page_payload, csrf_token)
        if response.get("code") == 403 or response.get("error_code") == 403:
            raise RuntimeError("企业主播接口 CSRF 校验失败，请重新扫码登录")

        data = response.get("data", {}) if isinstance(response, dict) else {}
        if not isinstance(data, dict):
            data = {}
        if self_profile is None and isinstance(data.get("self"), dict):
            self_profile = data["self"]

        page_rows = []
        for key in row_keys:
            value = data.get(key)
            if isinstance(value, list):
                page_rows.extend(item for item in value if isinstance(item, dict))

        added = 0
        for item in page_rows:
            identity = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
            if identity not in seen:
                seen.add(identity)
                rows.append(item)
                added += 1

        total = _safe_int(_first_value(data, "total", "totalCount", "total_count", "count"))
        has_more = _first_value(data, "hasMore", "has_more")
        if not page_rows or added == 0:
            break
        if total is not None and len(rows) >= total:
            break
        if has_more is False:
            break

    if len(rows) >= ENTERPRISE_PAGE_SIZE * ENTERPRISE_MAX_PAGES:
        logger.warning("企业接口达到最大分页限制: path=%s rows=%s", path, len(rows))
    return rows, self_profile


def _is_enterprise_live_status(value) -> bool:
    """企业后台当前以 2 表示直播中；兼容旧接口曾使用的 1。"""
    return str(value).strip().lower() in {"1", "2", "live", "living"}


def _apply_enterprise_profile_to_session(session: LiveSession, profile: dict) -> bool:
    """把员工主播接口的稳定资料写入场次。"""
    values = {
        "anchor_name": _first_value(profile, "iesName", "ies_name", "nickname", "name"),
        "anchor_nickname": _first_value(profile, "iesName", "ies_name", "nickname", "name"),
        "anchor_avatar_url": _first_value(profile, "avatarUrl", "avatar_url", "avatar"),
        "douyin_id": _first_value(profile, "iesUniqId", "iesId", "ies_id", "douyinId", "douyin_id"),
        "douyin_uid": _first_value(profile, "iesUid", "ies_uid", "uid", "id"),
    }
    return _apply_session_anchor_profile(session, values)


async def _sync_enterprise_anchor_sessions(
    db: Session,
    context: BrowserContext,
    room: LiveRoom,
    task_id: Optional[int] = None,
    sanitize_error=None,
) -> dict:
    """从企业主账号的员工接口同步主播与场次的真实映射。"""
    page = None
    try:
        page = await context.new_page()
        csrf_token = {"value": ""}

        def capture_csrf(request):
            if "/bff/statistic/live-comment/" in request.url:
                csrf_token["value"] = request.headers.get("x-csrftoken", "") or csrf_token["value"]

        page.on("request", capture_csrf)
        root_room_id = str(room.room_id_str or "").strip()
        if not root_room_id:
            return {"anchor_count": 0, "session_count": 0, "profile_count": 0}
        await page.goto(
            f"{COMMENT_URL}?roomId={root_room_id}&fullscreen=0",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        await asyncio.sleep(4)

        # 当前企业后台实际使用 feiyu_csrf_token；不同登录态下请求头可能尚未被页面触发，
        # 因此从页面 Cookie 再兜底读取一次，避免接口 403 被误判为空主播列表。
        if not csrf_token["value"]:
            csrf_token["value"] = await page.evaluate(
                """() => document.cookie.split(';').map(v => v.trim())
                  .find(v => /^(feiyu_csrf_token|csrf_token|csrftoken|csrf-token)=/i.test(v))
                  ?.split('=').slice(1).join('=') || ''"""
            )

        employee_rows, account_self = await _fetch_enterprise_rows(
            page,
            "/bff/statistic/live-comment/accounts",
            {"roomId": root_room_id},
            csrf_token["value"],
            row_keys=(
                "employeeList",
                "employee_list",
                "enterpiseList",
                "enterpriseList",
                "enterprise_list",
                "records",
                "list",
            ),
        )
        employees = ([account_self] if account_self else []) + employee_rows
        unique_employees = {}
        for item in employees:
            if not isinstance(item, dict):
                continue
            ies_uid = _first_value(item, "iesUid", "ies_uid", "uid", "id")
            if ies_uid not in (None, ""):
                unique_employees[str(ies_uid)] = item

        existing_sessions = {
            item.dashboard_url: item
            for item in db.query(LiveSession).filter(LiveSession.room_id == room.id).all()
            if item.dashboard_url
        }
        session_count = 0
        discovered_session_count = 0
        profile_count = 0
        for profile in unique_employees.values():
            ies_uid = str(_first_value(profile, "iesUid", "ies_uid", "uid", "id"))
            rows, _ = await _fetch_enterprise_rows(
                page,
                "/bff/statistic/live-comment/room-lists",
                {"iesUid": ies_uid},
                csrf_token["value"],
                row_keys=("roomLists", "roomList", "room_lists", "records", "list"),
            )
            unique_rows = {}
            for item in rows:
                child_room_id = str(_first_value(item, "roomId", "room_id", "id") or "").strip()
                if not child_room_id:
                    continue
                unique_rows[child_room_id] = item

            discovered_session_count += len(unique_rows)
            for child_room_id, item in unique_rows.items():
                dashboard_url = f"{LIVE_SCREEN_URL}?room_id={child_room_id}&fullscreen=0"
                session = existing_sessions.get(dashboard_url)
                if session is None:
                    session = LiveSession(room_id=room.id, dashboard_url=dashboard_url)
                    db.add(session)
                    existing_sessions[dashboard_url] = session
                    session_count += 1

                changed = _apply_enterprise_profile_to_session(session, profile)
                start_time = _parse_epoch_dt(
                    _first_value(item, "liveStartTime", "live_start_time", "startTime", "start_time")
                )
                end_time = _parse_epoch_dt(
                    _first_value(item, "liveEndTime", "live_end_time", "endTime", "end_time")
                )
                if start_time and session.live_start_time != start_time:
                    session.live_start_time = start_time
                    changed = True
                if end_time and session.live_end_time != end_time:
                    session.live_end_time = end_time
                    changed = True
                if start_time and end_time:
                    duration_seconds = max(0, int((end_time - start_time).total_seconds()))
                    if session.live_duration_seconds != duration_seconds:
                        session.live_duration_seconds = duration_seconds
                        changed = True
                title = _first_value(item, "title", "roomTitle", "room_title", "sessionTitle")
                if title and session.session_title != title:
                    session.session_title = str(title)[:200]
                    changed = True
                stream_url = _first_value(item, "streamUrl", "stream_url", "replayUrl", "replay_url")
                if stream_url and session.stream_url != stream_url:
                    session.stream_url = str(stream_url)[:2000]
                    changed = True
                live_status = _first_value(item, "liveStatus", "live_status", "status")
                session.live_status = (
                    "ended" if end_time
                    else ("live" if _is_enterprise_live_status(live_status) else session.live_status or "finished")
                )
                if changed:
                    profile_count += 1

        db.commit()
        db.add(
            ScraperLog(
                task_id=task_id,
                level="info",
                message=(
                    f"企业主播映射同步完成: 主播={len(unique_employees)}, "
                    f"发现场次={discovered_session_count}, 新场次={session_count}, 更新={profile_count}"
                ),
                raw_json={
                    "anchor_count": len(unique_employees),
                    "session_count": session_count,
                    "discovered_session_count": discovered_session_count,
                    "profile_count": profile_count,
                    "room_id": root_room_id,
                },
            )
        )
        db.commit()
        logger.info(
            "企业主播映射同步完成: anchors=%s, discovered_sessions=%s, new_sessions=%s, profiles_updated=%s",
            len(unique_employees),
            discovered_session_count,
            session_count,
            profile_count,
        )
        return {
            "anchor_count": len(unique_employees),
            "session_count": session_count,
            "discovered_session_count": discovered_session_count,
            "profile_count": profile_count,
        }
    except Exception as exc:
        db.rollback()
        compact_error = str(exc)
        if sanitize_error:
            compact_error = sanitize_error(exc)
        recoverable = _is_context_closed_message(exc)
        if not recoverable:
            db.add(ScraperLog(level="error", message=f"企业主播映射同步失败: {compact_error}"))
            db.commit()
        logger.warning("企业主播映射同步失败%s: %s", "，等待自动恢复" if recoverable else "", compact_error)
        return {
            "anchor_count": 0,
            "session_count": 0,
            "discovered_session_count": 0,
            "profile_count": 0,
            "error": compact_error,
        }
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass


async def discover_enterprise_live_sessions(context: BrowserContext, room: LiveRoom) -> list[dict]:
    """轻量读取企业账号下全部主播的最新场次，返回正在直播的场次。"""
    root_room_id = str(room.room_id_str or "").strip()
    if not root_room_id:
        return []

    page = await context.new_page()
    try:
        await page.goto(
            f"{COMMENT_URL}?roomId={root_room_id}&fullscreen=0",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        await page.wait_for_timeout(3000)
        csrf_token = await page.evaluate(
            """() => document.cookie.split(';').map(v => v.trim())
              .find(v => /^(feiyu_csrf_token|csrf_token|csrftoken|csrf-token)=/i.test(v))
              ?.split('=').slice(1).join('=') || ''"""
        )
        employee_rows, account_self = await _fetch_enterprise_rows(
            page,
            "/bff/statistic/live-comment/accounts",
            {"roomId": root_room_id},
            csrf_token,
            row_keys=(
                "employeeList", "employee_list", "enterpiseList", "enterpriseList",
                "enterprise_list", "records", "list",
            ),
        )
        profiles = ([account_self] if account_self else []) + employee_rows
        unique_profiles = {}
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            uid = _first_value(profile, "iesUid", "ies_uid", "uid", "id")
            if uid not in (None, ""):
                unique_profiles[str(uid)] = profile

        live_sessions = []
        for uid, profile in unique_profiles.items():
            rows, _ = await _fetch_enterprise_rows(
                page,
                "/bff/statistic/live-comment/room-lists",
                {"iesUid": uid},
                csrf_token,
                row_keys=("roomLists", "roomList", "room_lists", "records", "list"),
                max_pages=1,
            )
            for item in rows:
                child_room_id = str(_first_value(item, "roomId", "room_id", "id") or "").strip()
                end_time = _parse_epoch_dt(
                    _first_value(item, "liveEndTime", "live_end_time", "endTime", "end_time")
                )
                status = _first_value(item, "liveStatus", "live_status", "status")
                if not child_room_id or end_time or not _is_enterprise_live_status(status):
                    continue
                live_sessions.append({
                    "dashboard_url": f"{LIVE_SCREEN_URL}?room_id={child_room_id}&fullscreen=0",
                    "session_title": _first_value(item, "title", "roomTitle", "room_title", "sessionTitle"),
                    "live_start_time": _parse_epoch_dt(
                        _first_value(item, "liveStartTime", "live_start_time", "startTime", "start_time")
                    ),
                    "anchor_name": _first_value(profile, "iesName", "ies_name", "nickname", "name"),
                    "anchor_nickname": _first_value(profile, "iesName", "ies_name", "nickname", "name"),
                    "anchor_avatar_url": _first_value(profile, "avatarUrl", "avatar_url", "avatar"),
                    "douyin_id": _first_value(profile, "iesUniqId", "iesId", "ies_id", "douyinId", "douyin_id"),
                    "douyin_uid": uid,
                })
        return live_sessions
    finally:
        try:
            await page.close()
        except Exception as exc:
            if not _is_context_closed_message(exc):
                logger.debug("监控发现页面关闭失败: %s", exc)
