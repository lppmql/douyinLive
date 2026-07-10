"""
一键采集服务 — 采集所有主播的大屏数据

原则：
- room_id 只是访问大屏页的入口参数，不代表主播
- 所有场次信息（主播名称、直播标题、状态等）以页面实际数据为准
- 不硬编码/假设任何主播信息
"""
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import re
from urllib.parse import urlencode, urlparse, parse_qs
from urllib.request import Request, urlopen
from sqlalchemy.orm import Session
from playwright.async_api import BrowserContext

from app.core.logger import logger
from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.models.live_metrics import LiveMetric
from app.models.comments import Comment
from app.models.live_audience_profiles import LiveAudienceProfile
from app.models.stream_sources import StreamSource
from app.models.scraper_accounts import ScraperAccount
from app.models.scraper_logs import ScraperLog
from app.services.collector.browser import browser_manager

# 抖音企业号后台地址
LEADS_BASE = "https://leads.cluerich.com"
LIVE_SCREEN_URL = f"{LEADS_BASE}/pc/analysis/live-screen"
COMMENT_URL = f"{LEADS_BASE}/pc/analysis/live-comment"
HOME_URL = f"{LEADS_BASE}/pc/growth/home"
HISTORY_API_URL = f"{LEADS_BASE}/live_console/history"
HISTORY_DETAIL_BATCH_SIZE = 20
HISTORY_DETAIL_TIMEOUT_SECONDS = 20


async def collect_all(db: Session) -> dict:
    """
    一键采集所有房间的数据
    先访问大屏页，从页面实际数据中提取场次信息，再入库
    """
    # 1. 获取已登录账号，设置持久化上下文的 storage path
    account = db.query(ScraperAccount).filter(
        ScraperAccount.login_status == "logged_in"
    ).order_by(ScraperAccount.last_login_at.desc()).first()

    if not account or not account.storage_state_path:
        return {
            "total_rooms": 0,
            "collected_rooms": 0,
            "message": "没有已登录的采集账号，请先扫码登录",
            "results": [],
        }

    # 如果持久化上下文没有 storage_path，从 DB 恢复
    if not browser_manager._logged_in_storage_path:
        browser_manager._logged_in_storage_path = account.storage_state_path
    if not browser_manager._logged_in_account_id:
        browser_manager._logged_in_account_id = account.id

    # 2. 获取所有配置了 room_id 的房间
    rooms = (
        db.query(LiveRoom)
        .filter(LiveRoom.status == True, LiveRoom.room_id_str.isnot(None))
        .all()
    )

    if not rooms:
        return {
            "total_rooms": 0,
            "collected_rooms": 0,
            "message": "没有配置房间，请先在直播间管理添加 room_id",
            "results": [],
        }

    # 3. 获取持久化登录上下文（优先复用，自动验证 Cookie）
    context, is_valid, msg = await browser_manager.get_logged_in_context()
    if not is_valid:
        return {
            "total_rooms": len(rooms),
            "collected_rooms": 0,
            "message": msg or "登录已过期，请先在采集页面重新扫码登录",
            "results": [],
        }

    try:
        results = []
        for room in rooms:
            result = await _collect_room_data(db, context, room)
            results.append(result)

        history_sync = _sync_history_sessions(db, account, rooms[0])
        history_detail_progress = await _enrich_history_sessions(
            db,
            context,
            account,
            rooms[0],
            limit=HISTORY_DETAIL_BATCH_SIZE,
        )

        # 采集完成后刷新持久化 Cookie（延长有效期）
        await browser_manager.refresh_logged_in_state()

        collected = sum(1 for r in results if r.get("error") is None)
        return {
            "total_rooms": len(rooms),
            "collected_rooms": collected,
            "history_synced_count": history_sync,
            "history_detail_synced_count": history_detail_progress["enriched_count"],
            "history_detail_checked_count": history_detail_progress["checked_count"],
            "history_detail_remaining_count": history_detail_progress["remaining_count"],
            "history_detail_batch_size": history_detail_progress["batch_size"],
            "results": results,
        }
    finally:
        # 注意：不关闭 context！它被 browser_manager 持久化了
        pass


async def _collect_room_data(db: Session, context: BrowserContext, room: LiveRoom) -> dict:
    """采集单个房间的数据 — 以页面实际数据为准"""
    room_id = room.room_id_str
    # NOTE: anchor_name 不提前假设，从页面数据中提取

    logger.info(f"开始采集 room_id={room_id}")
    log_entry = ScraperLog(level="info", message=f"开始采集 room_id={room_id}")
    db.add(log_entry)
    db.commit()

    try:
        home_info = await _scrape_home_live_card(context)

        # 1. 先访问大屏页，捕获所有 API 数据和页面信息
        page_data = await _scrape_live_screen(context, room_id)
        room_profile = _merge_room_profile(page_data.get("room_profile", {}), home_info)

        # 2. 从页面数据中提取场次信息（主播名、场次标题、状态等）
        session_info = page_data.get("session_info", {})
        anchor_name = (
            session_info.get("anchor_name")
            or room_profile.get("anchor_name")
            or room_profile.get("anchor_nickname")
            or home_info.get("anchor_name")
            or room.anchor_name
            or room.account_name
            or room_id
        )
        session_title = (
            home_info.get("session_title")
            or session_info.get("session_title")
            or f"room_{room_id}"
        )
        is_live = bool(home_info.get("is_live") or session_info.get("is_live"))

        # 3. 创建或更新场次记录
        now = datetime.utcnow()
        session = _get_or_create_session(db, room, session_title, is_live, now)
        _apply_room_profile(room, room_profile, anchor_name)
        if is_live and session.live_status != "live":
            session.live_status = "live"
            if not session.live_start_time:
                session.live_start_time = now

        session.dashboard_url = f"{LIVE_SCREEN_URL}?room_id={room_id}&fullscreen=0"

        # 4. 入库采集到的指标
        metrics_count = _save_metrics(db, session.id, page_data.get("metrics", []))
        profiles_count = _save_profiles(db, session.id, page_data.get("profiles", []))

        # 5. 用汇总指标更新场次记录
        sm = page_data.get("summary_metrics", {})
        if home_info.get("total_viewers") is not None:
            sm["total_viewers"] = home_info["total_viewers"]
        if home_info.get("realtime_online_count") is not None:
            sm["realtime_online_count"] = home_info["realtime_online_count"]
        if home_info.get("leads_count") is not None:
            sm["leads_count"] = home_info["leads_count"]
        if sm.get("total_viewers") is not None:
            session.total_viewers = sm["total_viewers"]
        if sm.get("peak_online_count") is not None:
            session.peak_online_count = sm["peak_online_count"]
        if sm.get("realtime_online_count") is not None:
            session.realtime_online_count = sm["realtime_online_count"]
        if sm.get("avg_watch_seconds") is not None:
            session.avg_watch_seconds = float(sm["avg_watch_seconds"])
        if sm.get("ad_cost") is not None:
            session.ad_cost = float(sm["ad_cost"])
        if sm.get("new_followers") is not None:
            session.new_followers = sm["new_followers"]
        if sm.get("leads_count") is not None:
            session.leads_count = sm["leads_count"]
        if sm.get("comments_count") is not None:
            session.comments_count = sm["comments_count"]
        if sm.get("exposure_enter_rate") is not None:
            session.exposure_enter_rate = float(sm["exposure_enter_rate"])
        if sm.get("comment_rate") is not None:
            session.comment_rate = float(sm["comment_rate"])
        if sm.get("interaction_rate") is not None:
            session.interaction_rate = float(sm["interaction_rate"])

        # 6. 采集评论
        comments_data = await _scrape_comments(context, room_id)
        comments_count = _save_comments(db, session.id, comments_data)
        if comments_count:
            session.comments_count = max(session.comments_count or 0, comments_count)

        # 7. 采集流地址
        stream_url = await _scrape_stream_url(context, room_id)
        if stream_url:
            session.stream_url = stream_url[:2000]

        db.commit()

        logger.info(
            f"采集完成 room_id={room_id}, "
            f"主播={anchor_name}, 直播={is_live}, "
            f"指标={metrics_count}, 评论={comments_count}, 画像={profiles_count}"
        )
        log_entry = ScraperLog(
            level="info",
            message=f"采集完成: {anchor_name}, 指标={metrics_count}, 评论={comments_count}",
        )
        db.add(log_entry)
        db.commit()

        return {
            "room_id": room_id,
            "anchor_name": anchor_name,
            "anchor_nickname": room.anchor_nickname or "",
            "douyin_id": room.douyin_id or "",
            "is_live": is_live,
            "metrics_count": metrics_count,
            "comments_count": comments_count,
            "profiles_count": profiles_count,
            "session_id": session.id,
        }

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"采集 room_id={room_id} 失败: {e}\n{tb}")
        err_log = ScraperLog(level="error", message=f"采集失败 room_id={room_id}: {str(e)}")
        db.add(err_log)
        db.commit()
        return {"room_id": room_id, "error": str(e)}


# ==================== 页面采集 ====================


async def _scrape_live_screen(context: BrowserContext, room_id: str) -> dict:
    """
    访问大屏页，捕获所有数据，从中提取场次信息、指标、画像

    返回: {
        "session_info": {"anchor_name": str, "session_title": str, "is_live": bool},
        "room_profile": {"anchor_name": str, "anchor_nickname": str, "anchor_avatar_url": str, "douyin_id": str, "douyin_uid": str},
        "metrics": [LiveMetric 数据...],
        "summary_metrics": {"total_viewers": int, "peak_online_count": int, ...},
        "profiles": [LiveAudienceProfile 数据...],
        "is_logged_in": bool,
    }
    """
    url = f"{LIVE_SCREEN_URL}?room_id={room_id}&fullscreen=0"
    page = await context.new_page()
    captured_api = []

    async def on_response(resp):
        try:
            ct = resp.headers.get("content-type", "")
            if "json" in ct:
                data = await resp.json()
                captured_api.append({"url": resp.url, "data": data})
        except Exception:
            pass

    page.on("response", lambda r: asyncio.ensure_future(on_response(r)))

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(8)

        # 从页面 DOM 提取可见文本
        body_text = await page.evaluate("document.body?.innerText || ''")
        top_info = await page.evaluate(
            """
            () => {
              const anchorNode = document.querySelector('.leads-rimless-input-inner');
              const timeWrap = document.getElementById('dp_live_time');
              return {
                anchor_name: anchorNode ? anchorNode.innerText.trim() : '',
                time_text: timeWrap ? timeWrap.innerText.trim() : ''
              };
            }
            """
        )

        # ===== 检查是否在登录页 =====
        is_logged_in = True
        if "手机登录" in body_text or "邮箱登录" in body_text:
            is_logged_in = False
            logger.warning(f"room_id={room_id} 页面为登录页，Cookie 已过期")
    except Exception as e:
        logger.warning(f"大屏页加载异常: {e}")
        body_text = ""
        is_logged_in = False
    finally:
        await page.close()

    if not is_logged_in:
        return {"session_info": {}, "metrics": [], "profiles": [], "is_logged_in": False}

    # ===== 解析主播资料 / 场次信息 =====
    room_profile = {
        "anchor_name": None,
        "anchor_nickname": None,
        "anchor_avatar_url": None,
        "douyin_id": None,
        "douyin_uid": None,
    }
    session_info = {"anchor_name": None, "session_title": None, "is_live": False}

    # 尝试从 API 响应中提取场次信息
    for item in captured_api:
        data = item.get("data", {})
        url = item.get("url", "")
        if not isinstance(data, dict):
            continue

        inner = data.get("data", {})
        # API 返回的 data.data 可能是列表或其他类型，跳过非 dict
        if not isinstance(inner, dict):
            continue

        # 检查是否有主播/场次信息
        anchor = inner.get("anchor_name") or inner.get("nickname") or inner.get("author_name")
        if anchor:
            session_info["anchor_name"] = anchor

        room_info = inner.get("roomInfo") or {}
        commerce_info = inner.get("commerceInfo") or {}
        if isinstance(room_info, dict):
            if room_info.get("ownerIesUid"):
                room_profile["douyin_uid"] = str(room_info.get("ownerIesUid"))
            if room_info.get("title"):
                session_info["session_title"] = room_info.get("title")
        if isinstance(commerce_info, dict):
            if commerce_info.get("iesName"):
                room_profile["anchor_nickname"] = commerce_info.get("iesName")
                room_profile["anchor_name"] = commerce_info.get("iesName")
                session_info["anchor_name"] = session_info["anchor_name"] or commerce_info.get("iesName")
            if commerce_info.get("avatarUrl"):
                room_profile["anchor_avatar_url"] = commerce_info.get("avatarUrl")
            if commerce_info.get("iesUniqId"):
                room_profile["douyin_id"] = commerce_info.get("iesUniqId")
            if commerce_info.get("iesUid"):
                room_profile["douyin_uid"] = str(commerce_info.get("iesUid"))

        title = inner.get("title") or inner.get("room_title") or inner.get("session_title")
        if title:
            session_info["session_title"] = title

        # 检查直播状态
        live_status = inner.get("live_status") or inner.get("status")
        if live_status is not None:
            session_info["is_live"] = (live_status == 1 or live_status is True)

    # DOM 降级：从页面文本提取主播名
    if top_info.get("anchor_name"):
        session_info["anchor_name"] = top_info["anchor_name"]

    if not session_info["anchor_name"] and body_text:
        for line in body_text.split("\n"):
            line = line.strip()
            if line and len(line) <= 20 and "主播" in line:
                session_info["anchor_name"] = line.replace("主播", "").strip()
                break

    if top_info.get("time_text"):
        session_info["session_title"] = top_info["time_text"]

    # ===== 解析指标 =====
    metrics = []
    metric_time = datetime.utcnow()

    # 从 API 响应中提取实时指标
    for item in captured_api:
        data = item.get("data", {})
        if not isinstance(data, dict):
            continue
        inner = data.get("data", {}) or {}
        if not isinstance(inner, dict):
            continue

        # 提取 field:value 格式的指标（基于大屏页 API 真实 key）
        fields_map = {
            # 流量趋势（LiveMetric 全部字段）
            "online_count": ["lp_screen_live_user_realtime", "online_count", "online", "user_realtime"],
            "exposure_count": ["lp_screen_live_enter_users", "exposure_count", "exposure"],
            "enter_count": ["lp_screen_live_enter_users", "enter_count"],
            "enter_fans_count": ["lp_screen_live_enter_fans", "enter_fans_count", "enter_fans"],
            "leave_count": ["lp_screen_live_leave_users", "leave_count", "leave"],
            "like_count": ["lp_screen_live_like_count", "like_count"],
            "comment_count": ["lp_screen_live_comment_count", "comment_count"],
            "follow_count": ["lp_screen_live_new_follow_count", "follow_count", "new_follow"],
            "natural_traffic_count": ["natural_traffic", "natural_traffic_count"],
            "marketing_traffic_count": ["marketing_traffic", "marketing_traffic_count"],
        }

        metric_values = {}
        for field, keys in fields_map.items():
            for key in keys:
                val = inner.get(key)
                if val is not None:
                    metric_values[field] = _safe_int(val)
                    break

        if metric_values.get("online_count") or metric_values.get("enter_count"):
            metrics.append(LiveMetric(session_id=0, metric_time=metric_time, **metric_values))

    # ===== 提取场次汇总指标（更新 LiveSession） =====
    summary_metrics = {}
    for item in captured_api:
        data = item.get("data", {})
        if not isinstance(data, dict):
            continue
        inner = data.get("data", {}) or data
        if not isinstance(inner, dict):
            continue

        # 收集所有数值型 key-value
        for key, val in inner.items():
            if key in summary_metrics:
                continue
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                summary_metrics[key] = val

    # 将 Cluerich key 映射到 LiveSession 字段
    session_field_map = {
        "total_viewers": ["accumulate_view_users", "cumulate_view_users", "view_users", "total_viewers"],
        "peak_online_count": ["lp_screen_live_peak_online", "peak_online", "peak_online_count", "max_online"],
        "realtime_online_count": ["lp_screen_live_user_realtime", "realtime_online", "online_count"],
        "avg_watch_seconds": ["lp_screen_live_avg_watch_duration", "avg_watch_duration", "avg_watch_seconds"],
        "ad_cost": ["lp_screen_live_ad_cost", "ad_cost", "cost_total"],
        "new_followers": ["lp_screen_live_new_follow_count", "new_followers", "new_follow_count"],
        "leads_count": ["lp_screen_clue_uv", "leads_count", "clue_count", "clue_uv"],
        "comments_count": ["lp_screen_live_comment_count", "comments_count"],
        "exposure_enter_rate": ["lp_screen_live_exposure_enter_rate", "exposure_enter_rate"],
        "comment_rate": ["lp_screen_live_comment_rate", "comment_rate"],
        "interaction_rate": ["lp_screen_live_interaction_rate", "interaction_rate"],
    }
    mapped_summary = {}
    for field, api_keys in session_field_map.items():
        for key in api_keys:
            if key in summary_metrics:
                mapped_summary[field] = summary_metrics[key]
                break

    # ===== 解析画像 =====
    profiles = []
    for item in captured_api:
        data = item.get("data", {})
        if not isinstance(data, dict):
            continue
        inner = data.get("data", {})
        if not isinstance(inner, dict):
            continue

        for dim in ("age", "gender", "region", "province", "city", "device", "interest"):
            dim_data = inner.get(dim) or inner.get(f"lp_screen_{dim}")
            if dim_data and isinstance(dim_data, list):
                for entry in dim_data:
                    if isinstance(entry, dict):
                        profiles.append({
                            "dimension_type": dim,
                            "dimension_name": entry.get("name", ""),
                            "ratio": float(entry.get("ratio", entry.get("value", 0)) or 0),
                            "count": _safe_int(entry.get("count", 0)),
                        })

    # 如果页面文本包含 "直播中"，标记为直播
    if "直播中" in body_text or "正在直播" in body_text:
        session_info["is_live"] = True

    return {
        "session_info": session_info,
        "room_profile": room_profile,
        "metrics": metrics,
        "summary_metrics": mapped_summary,
        "profiles": profiles,
    }


async def _scrape_comments(context: BrowserContext, room_id: str) -> list:
    """访问评论页，采集评论数据"""
    url = f"{COMMENT_URL}?roomId={room_id}&fullscreen=0"
    page = await context.new_page()
    captured_api = []

    async def on_response(resp):
        try:
            ct = resp.headers.get("content-type", "")
            if "json" in ct:
                d = await resp.json()
                captured_api.append(d)
        except Exception:
            pass

    page.on("response", lambda r: asyncio.ensure_future(on_response(r)))

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(6)
    except Exception:
        pass
    finally:
        await page.close()

    comments = []
    for data in captured_api:
        if not isinstance(data, dict):
            continue
        inner = data.get("data", {}) or {}

        comment_list = None
        if isinstance(inner, list):
            comment_list = inner
        elif isinstance(inner, dict):
            comment_list = inner.get("list") or inner.get("comments") or inner.get("rows")

        if comment_list and isinstance(comment_list, list):
            for c in comment_list:
                if not isinstance(c, dict):
                    continue
                comments.append({
                    "user_nickname": c.get("user_nickname") or c.get("nickname") or "",
                    "comment_content": c.get("comment_content") or c.get("content") or "",
                    "comment_time": c.get("comment_time"),
                })

    return comments


async def _scrape_home_live_card(context: BrowserContext) -> dict:
    """从主页直播卡片提取主播、标题、实时人数等稳定信息。"""
    page = await context.new_page()
    captured_api = []

    async def on_response(resp):
        try:
            if "json" in resp.headers.get("content-type", ""):
                captured_api.append(await resp.json())
        except Exception:
            pass

    page.on("response", lambda r: asyncio.ensure_future(on_response(r)))
    try:
        await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        body_text = await page.evaluate("document.body?.innerText || ''")
    except Exception:
        return {}
    finally:
        await page.close()

    lines = [line.strip() for line in body_text.split("\n") if line.strip()]
    info = {
        "anchor_name": None,
        "anchor_nickname": None,
        "anchor_avatar_url": None,
        "douyin_id": None,
        "douyin_uid": None,
        "session_title": None,
        "is_live": False,
        "realtime_online_count": None,
        "total_viewers": None,
        "leads_count": None,
    }

    if "您当前正在直播，更多详情" in lines:
        info["is_live"] = True
    if "直播中" in lines:
        info["is_live"] = True
        idx = lines.index("直播中")
        if idx + 1 < len(lines):
            info["session_title"] = lines[idx + 1]
        if idx + 2 < len(lines):
            info["anchor_name"] = lines[idx + 2]

    label_map = {
        "当前观看人数": "realtime_online_count",
        "累计观看人数": "total_viewers",
        "留资线索数": "leads_count",
    }
    for label, field in label_map.items():
        value = _extract_next_number(lines, label)
        if value is not None:
            info[field] = value

    for payload in captured_api:
        if not isinstance(payload, dict):
            continue
        inner = payload.get("data", {}) or {}
        if not isinstance(inner, dict):
            continue
        if inner.get("nick_name"):
            info["anchor_nickname"] = inner.get("nick_name")
        if inner.get("avatar_url"):
            info["anchor_avatar_url"] = inner.get("avatar_url")
        if inner.get("douyin_unique_id"):
            info["douyin_id"] = inner.get("douyin_unique_id")
        if inner.get("douyin_uid"):
            info["douyin_uid"] = str(inner.get("douyin_uid"))

    return info


def _sync_history_sessions(db: Session, account: ScraperAccount, room: LiveRoom) -> int:
    """同步当前账号下的历史直播场次到 live_sessions。"""
    storage_path = account.storage_state_path or ""
    cookie_jar = _load_storage_cookies(storage_path)
    if not cookie_jar:
        logger.warning("历史场次同步跳过：未找到可用 Cookie")
        return 0

    existing_sessions = {
        row.dashboard_url: row
        for row in db.query(LiveSession).filter(LiveSession.room_id == room.id).all()
        if row.dashboard_url
    }
    page_no = 1
    limit = 100
    total = None
    synced = 0

    while total is None or (page_no - 1) * limit < total:
        query = urlencode({"total": 0, "limit": limit, "page": page_no})
        req = Request(
            f"{HISTORY_API_URL}?{query}",
            headers={
                "Cookie": "; ".join(f"{k}={v}" for k, v in cookie_jar.items()),
                "User-Agent": account.user_agent or "Mozilla/5.0",
                "Accept": "application/json,text/plain,*/*",
            },
        )
        with urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        data = (payload or {}).get("data", {}) or {}
        history_rows = data.get("live_history") or []
        total = data.get("total_count") or 0

        if not history_rows:
            break

        for item in history_rows:
            history_room_id = str(item.get("room_id") or "").strip()
            if not history_room_id:
                continue

            dashboard_url = f"{LIVE_SCREEN_URL}?room_id={history_room_id}&fullscreen=0"
            session = existing_sessions.get(dashboard_url)
            if session is None:
                session = LiveSession(room_id=room.id, dashboard_url=dashboard_url)
                db.add(session)
                existing_sessions[dashboard_url] = session
                synced += 1

            start_time = _parse_dt(item.get("start_time"))
            end_time = _parse_dt(item.get("end_time"))
            session.session_title = (
                session.session_title
                or (f"历史直播 {item.get('start_time')}" if item.get("start_time") else f"room_{history_room_id}")
            )
            session.stream_url = item.get("room_videorecord") or session.stream_url or None
            session.live_start_time = start_time or session.live_start_time
            session.live_end_time = end_time or session.live_end_time
            session.live_duration_seconds = _safe_int(item.get("live_time")) or session.live_duration_seconds or 0
            session.live_status = "ended" if end_time else (session.live_status or "finished")
            session.total_viewers = _safe_int(item.get("total_audience")) or session.total_viewers or 0
            avg_live_duration = _safe_int(item.get("avg_live_duration"))
            if avg_live_duration is not None:
                session.avg_watch_seconds = float(avg_live_duration)
            session.leads_count = _safe_int(item.get("live_leads_info_cnt")) or session.leads_count or 0
            session.private_message_count = _safe_int(item.get("consultation_count")) or session.private_message_count or 0

        page_no += 1

    db.commit()
    return synced


async def _enrich_history_sessions(
    db: Session,
    context: BrowserContext,
    account: ScraperAccount,
    room: LiveRoom,
    limit: int = HISTORY_DETAIL_BATCH_SIZE,
) -> dict:
    """补齐历史场次的大屏详情、回放流和评论。"""
    del account
    all_sessions = (
        db.query(LiveSession)
        .filter(
            LiveSession.room_id == room.id,
            LiveSession.live_start_time.isnot(None),
            LiveSession.live_end_time.isnot(None),
        )
        .order_by(LiveSession.live_start_time.desc())
        .all()
    )

    pending_sessions = [session for session in all_sessions if _needs_history_enrichment(session)]
    target_sessions = pending_sessions[:limit]
    enriched = 0
    checked = 0
    consecutive_mismatch = 0
    for session in target_sessions:
        room_id = _extract_room_id_from_dashboard_url(session.dashboard_url)
        if not room_id:
            continue

        checked += 1
        try:
            detail = await asyncio.wait_for(
                _scrape_history_session_detail(context, room_id, session),
                timeout=HISTORY_DETAIL_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("历史场次详情采集超时，跳过: session_id=%s room_id=%s", session.id, room_id)
            continue

        if detail.get("validation_failed"):
            consecutive_mismatch += 1
            if consecutive_mismatch >= 5:
                logger.info("历史详情连续 %s 场校验失败，停止继续补齐更早场次", consecutive_mismatch)
                break
            continue

        consecutive_mismatch = 0
        overview = detail.get("overview", {})
        trend_rows = detail.get("trend", [])
        replay_url = detail.get("replay_url")
        comments_data = detail.get("comments", [])

        changed = _apply_overview_to_session(session, overview)
        if replay_url and session.stream_url != replay_url:
            session.stream_url = replay_url[:2000]
            changed = True

        metrics_count = _save_trend_metrics(db, session.id, trend_rows)
        comments_count = _save_comments(db, session.id, comments_data)
        if comments_count:
            session.comments_count = max(session.comments_count or 0, comments_count)
            changed = True

        if changed or metrics_count or comments_count:
            db.commit()
            enriched += 1

    return {
        "enriched_count": enriched,
        "checked_count": checked,
        "remaining_count": max(len(pending_sessions) - checked, 0),
        "batch_size": limit,
    }


async def _fetch_json(page, url: str) -> dict:
    """在已登录浏览器上下文里执行 fetch，避免单独维护 Cookie。"""
    try:
        result = await page.evaluate(
            """
            async (targetUrl) => {
              const resp = await fetch(targetUrl, { credentials: 'include' });
              return await resp.json();
            }
            """,
            url,
        )
        if isinstance(result, dict):
            return result
    except Exception as exc:
        logger.warning(f"fetch json 失败: {url}, error={exc}")
    return {}


async def _scrape_history_session_detail(
    context: BrowserContext,
    room_id: str,
    session: LiveSession,
) -> dict:
    """从历史大屏页提取总览、趋势、回放流和评论。"""
    url = f"{LIVE_SCREEN_URL}?room_id={room_id}&fullscreen=0"
    page = await context.new_page()
    hits = {}

    async def on_response(resp):
        try:
            if "json" not in resp.headers.get("content-type", ""):
                return
            if "/bff/statistic/live-screen/overview" in resp.url:
                hits["overview"] = await resp.json()
            elif "/bff/statistic/live-screen/data" in resp.url:
                hits["data"] = await resp.json()
            elif "/bff/statistic/live-screen/v3/get-live-replay" in resp.url:
                hits["replay"] = await resp.json()
        except Exception:
            pass

    page.on("response", lambda r: asyncio.ensure_future(on_response(r)))
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(6)
        try:
            await page.get_by_text("评论", exact=True).click(timeout=5000)
            await asyncio.sleep(3)
        except Exception:
            pass

        body_text = await page.evaluate("document.body?.innerText || ''")
        if not _is_expected_history_session(body_text, session):
            logger.warning(
                "历史场次详情页校验失败，跳过写入: session_id=%s room_id=%s",
                session.id,
                room_id,
            )
            return {
                "overview": {},
                "trend": [],
                "replay_url": None,
                "comments": [],
                "validation_failed": True,
            }

        overview_rows = (((hits.get("overview") or {}).get("data", {}) or {}).get("statRows")) or []
        trend_rows = (((hits.get("data") or {}).get("data", {}) or {}).get("trend")) or []
        replay_url = (((hits.get("replay") or {}).get("data", {}) or {}).get("replayUrl")) or None
        comments = _parse_comments_from_live_screen_text(body_text, session.live_start_time)
        return {
            "overview": overview_rows[0] if overview_rows else {},
            "trend": trend_rows,
            "replay_url": replay_url,
            "comments": comments,
        }
    except Exception:
        return {"overview": {}, "trend": [], "replay_url": None, "comments": [], "validation_failed": False}
    finally:
        await page.close()


async def _scrape_stream_url(context: BrowserContext, room_id: str) -> Optional[str]:
    """采集 m3u8 流地址"""
    url = f"{LIVE_SCREEN_URL}?room_id={room_id}&fullscreen=0"
    page = await context.new_page()
    m3u8_urls = []

    def on_request(req):
        if ".m3u8" in req.url:
            m3u8_urls.append(req.url)

    page.on("request", on_request)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        return m3u8_urls[-1] if m3u8_urls else None
    except Exception:
        return None
    finally:
        await page.close()


# ==================== 数据入库 ====================


def _get_or_create_session(
    db: Session, room: LiveRoom, session_title: str, is_live: bool, now: datetime
) -> LiveSession:
    """根据页面数据获取或创建场次"""
    # 找最新的活跃场次
    session = (
        db.query(LiveSession)
        .filter(
            LiveSession.room_id == room.id,
            LiveSession.live_status.in_(["live", "scheduled"]),
        )
        .order_by(LiveSession.live_start_time.desc())
        .first()
    )

    if not session:
        session = (
            db.query(LiveSession)
            .filter(LiveSession.room_id == room.id)
            .order_by(LiveSession.live_start_time.desc())
            .first()
        )

    if not session:
        session = LiveSession(
            room_id=room.id,
            session_title=session_title,
            live_status="live" if is_live else "scheduled",
            live_start_time=now if is_live else None,
        )
        db.add(session)
        db.commit()
        db.refresh(session)

    return session


def _upsert_history_session(
    db: Session,
    room: LiveRoom,
    item: dict,
) -> bool:
    """把历史直播列表中的一条记录同步到 LiveSession。"""
    history_room_id = str(item.get("room_id") or "").strip()
    if not history_room_id:
        return False

    dashboard_url = f"{LIVE_SCREEN_URL}?room_id={history_room_id}&fullscreen=0"
    session = (
        db.query(LiveSession)
        .filter(
            LiveSession.room_id == room.id,
            LiveSession.dashboard_url == dashboard_url,
        )
        .first()
    )

    created = session is None
    if session is None:
        session = LiveSession(room_id=room.id, dashboard_url=dashboard_url)
        db.add(session)

    start_time = _parse_dt(item.get("start_time"))
    end_time = _parse_dt(item.get("end_time"))
    session.session_title = (
        session.session_title
        or (f"历史直播 {item.get('start_time')}" if item.get("start_time") else f"room_{history_room_id}")
    )
    session.stream_url = item.get("room_videorecord") or session.stream_url or None
    session.live_start_time = start_time or session.live_start_time
    session.live_end_time = end_time or session.live_end_time
    session.live_duration_seconds = _safe_int(item.get("live_time")) or session.live_duration_seconds or 0
    session.live_status = "ended" if end_time else (session.live_status or "finished")
    session.total_viewers = _safe_int(item.get("total_audience")) or session.total_viewers or 0
    avg_live_duration = _safe_int(item.get("avg_live_duration"))
    if avg_live_duration is not None:
        session.avg_watch_seconds = float(avg_live_duration)
    session.leads_count = _safe_int(item.get("live_leads_info_cnt")) or session.leads_count or 0
    session.private_message_count = _safe_int(item.get("consultation_count")) or session.private_message_count or 0

    db.commit()
    return created


def _save_metrics(db: Session, session_id: int, metrics: list) -> int:
    """保存指标数据"""
    count = 0
    for m in metrics:
        m.session_id = session_id
        db.add(m)
        count += 1
    if count:
        db.commit()
    return count


def _save_trend_metrics(db: Session, session_id: int, trend_rows: list[dict]) -> int:
    """保存历史场次分钟级趋势指标，避免重复写入。"""
    if not trend_rows:
        return 0

    existing_times = {
        row[0]
        for row in db.query(LiveMetric.metric_time).filter(LiveMetric.session_id == session_id).all()
    }
    count = 0
    for item in trend_rows:
        dimensions = item.get("dimensions", {}) or {}
        metrics = item.get("metrics", {}) or {}
        stat_time_minute = dimensions.get("stat_time_minute")
        if not stat_time_minute:
            continue
        metric_time = datetime.fromtimestamp(int(stat_time_minute) / 1000)
        if metric_time in existing_times:
            continue

        row = LiveMetric(
            session_id=session_id,
            metric_time=metric_time,
            exposure_count=_safe_int(metrics.get("lp_screen_live_show_count")) or 0,
            online_count=_safe_int(metrics.get("lp_screen_live_max_watch_uv_by_minute")) or 0,
            enter_count=_safe_int(metrics.get("lp_screen_live_watch_uv_by_minute")) or 0,
            enter_fans_count=_safe_int(metrics.get("lp_screen_live_fans_watch_uv_by_minute")) or 0,
            leave_count=_safe_int(metrics.get("lp_screen_live_leave_uv_by_minute")) or 0,
            like_count=_safe_int(metrics.get("lp_screen_live_like_count")) or 0,
            comment_count=_safe_int(metrics.get("lp_screen_live_comment_count")) or 0,
            follow_count=_safe_int(metrics.get("lp_screen_live_follow_count")) or 0,
            natural_traffic_count=_safe_int(metrics.get("lp_screen_live_watch_count_natural")) or 0,
            marketing_traffic_count=_safe_int(metrics.get("lp_screen_live_watch_count_ad")) or 0,
        )
        db.add(row)
        count += 1

    if count:
        db.commit()
    return count


def _save_comments(db: Session, session_id: int, comments: list) -> int:
    """保存评论数据"""
    existing_pairs = {
        _comment_identity(row.comment_content or "", row.comment_time)
        for row in db.query(Comment).filter(Comment.session_id == session_id).all()
    }
    seen_pairs = set()
    count = 0
    for c in comments:
        content = c.get("comment_content", "").strip()
        comment_time = c.get("comment_time")
        if not content:
            continue

        pair = _comment_identity(content, comment_time)
        if pair in existing_pairs or pair in seen_pairs:
            continue
        seen_pairs.add(pair)

        if content:
            comment = Comment(
                session_id=session_id,
                user_nickname=c.get("user_nickname", "未知"),
                comment_content=content,
                comment_time=comment_time or datetime.utcnow(),
            )
            db.add(comment)
            count += 1
    if count:
        db.commit()
    return count


def _save_profiles(db: Session, session_id: int, profiles: list) -> int:
    """保存画像数据"""
    count = 0
    for p in profiles:
        profile = LiveAudienceProfile(
            session_id=session_id,
            dimension_type=p["dimension_type"],
            dimension_name=p["dimension_name"],
            ratio=p["ratio"],
            count=p["count"],
        )
        db.add(profile)
        count += 1
    if count:
        db.commit()
    return count


def _safe_int(val) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(float(str(val).replace(",", "")))
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


def _parse_dt(val: Optional[str]) -> Optional[datetime]:
    if not val:
        return None
    try:
        return datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _extract_room_id_from_dashboard_url(url: Optional[str]) -> Optional[str]:
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


def _is_expected_history_session(body_text: str, session: LiveSession) -> bool:
    """校验当前详情页是否真的是目标场次，避免历史页面串场写错数据。"""
    if not body_text or not session.live_start_time or not session.live_end_time:
        return False

    normalized_text = body_text.replace("：", ":").replace("〜", "~").replace("～", "~")
    for expected in _build_expected_session_markers(session.live_start_time, session.live_end_time):
        if expected in normalized_text:
            return True

    markers = _build_expected_session_markers(session.live_start_time, session.live_end_time)
    logger.warning(
        "历史场次时间段未命中: session_id=%s, sample_expected=%s",
        session.id,
        markers[:6],
    )
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


def _apply_overview_to_session(session: LiveSession, overview_row: dict) -> bool:
    metrics = overview_row.get("metrics", {}) or {}
    changed = False

    mapping = {
        "total_viewers": "lp_screen_live_watch_uv",
        "peak_online_count": "lp_screen_live_max_watch_uv_by_minute",
        "realtime_online_count": "lp_screen_live_user_realtime",
        "private_message_count": "lp_screen_msg_conversation_count",
        "scene_leads_count": "lp_screen_clue_uv",
        "leads_count": "lp_screen_clue_uv",
        "mini_windmill_click_count": "lp_screen_live_icon_click_count",
        "new_followers": "lp_screen_live_follow_uv",
        "comments_count": "lp_screen_live_comment_count",
    }
    for field, key in mapping.items():
        value = _safe_int(metrics.get(key))
        if value is not None and getattr(session, field) != value:
            setattr(session, field, value)
            changed = True

    float_mapping = {
        "avg_watch_seconds": "lp_screen_live_avg_watch_duration",
        "ad_cost": "lp_screen_live_stat_cost",
        "exposure_enter_rate": "lp_screen_live_enter_ratio",
        "comment_rate": "lp_screen_live_comment_ratio",
        "interaction_rate": "lp_screen_live_interaction_ratio",
        "share_rate": "lp_screen_live_share_ratio",
        "like_rate": "lp_screen_live_like_ratio",
    }
    for field, key in float_mapping.items():
        raw = metrics.get(key)
        if raw is None:
            continue
        value = float(raw)
        if getattr(session, field) != value:
            setattr(session, field, value)
            changed = True

    session.live_status = "ended" if session.live_end_time else session.live_status
    return changed


def _apply_room_profile(room: LiveRoom, room_profile: dict, anchor_name: str) -> None:
    """把本次真实采集到的主播资料写回直播间主表。"""
    room.anchor_name = anchor_name or room.anchor_name
    if room_profile.get("anchor_nickname"):
        room.anchor_nickname = room_profile["anchor_nickname"]
    if room_profile.get("anchor_avatar_url"):
        room.anchor_avatar_url = room_profile["anchor_avatar_url"][:500]
    if room_profile.get("douyin_id"):
        room.douyin_id = room_profile["douyin_id"]
    if room_profile.get("douyin_uid"):
        room.douyin_uid = room_profile["douyin_uid"]


def _merge_room_profile(primary: dict, fallback: dict) -> dict:
    """优先用房间级主播资料，缺失时回退到账号首页资料。"""
    merged = dict(primary or {})
    fallback = fallback or {}
    for key in ("anchor_name", "anchor_nickname", "anchor_avatar_url", "douyin_id", "douyin_uid"):
        if not merged.get(key) and fallback.get(key):
            merged[key] = fallback.get(key)
    return merged


def _needs_history_enrichment(session: LiveSession) -> bool:
    """判断历史场次是否还需要继续补齐详情。"""
    return not (
        (session.peak_online_count or 0) > 0
        and (session.comments_count or 0) > 0
        and bool(session.stream_url)
    )


def _parse_comments_from_live_screen_text(body_text: str, live_start_time: Optional[datetime]) -> list[dict]:
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


def _load_storage_cookies(storage_state_path: str) -> dict[str, str]:
    """从 Playwright storage_state 文件中提取 Cookie。"""
    if not storage_state_path:
        return {}
    path = Path(storage_state_path)
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"读取 storage_state 失败: {storage_state_path}, error={exc}")
        return {}

    cookies = {}
    for item in payload.get("cookies", []) or []:
        name = item.get("name")
        value = item.get("value")
        if name and value:
            cookies[name] = value
    return cookies


def _comment_identity(content: str, comment_time: Optional[datetime]) -> tuple[str, Optional[datetime]]:
    """没有真实评论时间时，退化为仅按内容去重，避免重复采集整批旧评论。"""
    normalized_time = comment_time.replace(microsecond=0) if isinstance(comment_time, datetime) else None
    return (content, normalized_time)
