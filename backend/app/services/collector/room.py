"""
页面抓取 — 从 manual_collect.py 提取

负责：大屏页数据捕获、主页直播卡片、流地址抓取、历史场次详情、评论接口分页读取
"""
import asyncio
from datetime import datetime
from typing import Optional

from playwright.async_api import BrowserContext

from app.core.logger import logger
from app.models.live_metrics import LiveMetric
from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.services.collector.comments import _parse_comment_user_profile, _parse_comments_from_live_screen_text
from app.services.collector.metrics import _parse_watch_profiles
from app.services.collector.utils import (
    _is_context_closed_message,
    _parse_comment_time,
    _safe_int,
)

# 大屏页 + 主页地址
from app.services.collector.constants import LIVE_SCREEN_URL
HOME_URL = "https://leads.cluerich.com/pc/growth/home"


# ==================== 页面抓取 ====================


async def _drain_response_tasks(tasks: list[asyncio.Task], timeout_seconds: float = 3) -> None:
    """回收响应解析任务，避免页面或驱动关闭后留下未读取的异步异常。"""
    if not tasks:
        return
    _done, pending = await asyncio.wait(tasks, timeout=timeout_seconds)
    for task in pending:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


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
    response_tasks = []

    async def on_response(resp):
        try:
            ct = resp.headers.get("content-type", "")
            if "json" in ct:
                data = await asyncio.wait_for(resp.json(), timeout=3)
                captured_api.append({"url": resp.url, "data": data})
        except Exception:
            pass

    page.on("response", lambda r: response_tasks.append(asyncio.create_task(on_response(r))))

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
        await asyncio.sleep(0.5)
        await _drain_response_tasks(response_tasks)
    except Exception as e:
        logger.warning(f"大屏页加载异常: {e}")
        body_text = ""
        is_logged_in = False
    finally:
        try:
            await page.close()
        except Exception as exc:
            if not _is_context_closed_message(exc):
                logger.debug("大屏页面关闭失败: %s", exc)
        await _drain_response_tasks(response_tasks)

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
            "clue_count": ["lp_screen_clue_uv", "clue_count"],
            "windmill_click_count": ["lp_screen_live_icon_click_count", "windmill_click_count"],
            "card_click_count": ["lp_screen_live_clue_business_card_click_count", "card_click_count"],
            "wechat_add_count": ["lp_screen_ad_biz_wechat_add_count", "wechat_add_count"],
            "form_submit_count": ["lp_screen_ad_form_count", "form_submit_count"],
            "form_submit_users": ["lp_screen_card_clue_uv", "form_submit_users"],
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
        "viewed_count": ["lp_screen_uv_with_preview", "viewed_count"],
        "avg_online_count": ["lp_screen_live_avg_online_uv_by_room", "avg_online_count"],
        "peak_online_count": ["lp_screen_live_peak_online", "peak_online", "peak_online_count", "max_online"],
        "realtime_online_count": ["lp_screen_live_user_realtime", "realtime_online", "online_count"],
        "avg_watch_seconds": ["lp_screen_live_avg_watch_duration", "avg_watch_duration", "avg_watch_seconds"],
        "fans_avg_watch_seconds": ["lp_screen_live_fans_avg_watch_duration", "fans_avg_watch_seconds"],
        "private_message_count": ["lp_screen_msg_conversation_count", "private_message_count"],
        "private_message_longterm_count": ["lp_screen_longterm_msg_clue_uv", "private_message_longterm_count"],
        "scene_leads_count": ["lp_screen_clue_uv", "scene_leads_count"],
        "ad_cost": ["lp_screen_live_ad_cost", "ad_cost", "cost_total"],
        "mini_windmill_click_count": ["lp_screen_live_icon_click_count", "mini_windmill_click_count"],
        "mini_windmill_click_rate": ["lp_screen_live_icon_click_rate", "mini_windmill_click_rate"],
        "card_click_count": ["lp_screen_live_clue_business_card_click_count", "card_click_count"],
        "card_click_rate": ["lp_screen_live_clue_business_card_click_rate", "card_click_rate"],
        "new_followers": ["lp_screen_live_new_follow_count", "new_followers", "new_follow_count"],
        "follow_rate": ["lp_screen_live_follow_ratio", "follow_rate"],
        "share_count": ["lp_screen_live_share_count", "share_count"],
        "share_users": ["lp_screen_live_share_uv", "share_users"],
        "like_count": ["lp_screen_live_like_count", "like_count"],
        "like_users": ["lp_screen_live_like_uv", "like_users"],
        "leads_count": ["lp_screen_clue_uv", "leads_count", "clue_count", "clue_uv"],
        "comments_count": ["lp_screen_live_comment_count", "comments_count"],
        "comment_users": ["lp_screen_live_comment_uv", "comment_users"],
        "interaction_count": ["lp_screen_live_interaction_count", "interaction_count"],
        "interaction_users": ["lp_screen_live_interaction_uv_count", "interaction_users"],
        "watch_count": ["lp_screen_live_watch_count", "watch_count"],
        "watch_over_1m_count": ["lp_screen_live_watch_gt_1min_count", "watch_over_1m_count"],
        "fans_club_join_count": ["lp_screen_live_fans_club_join_uv", "fans_club_join_count"],
        "fans_club_join_rate": ["lp_screen_live_fans_club_join_uv_ratio", "fans_club_join_rate"],
        "gift_count": ["lp_screen_live_gift_count", "gift_count"],
        "gift_amount": ["lp_screen_live_gift_amount", "gift_amount"],
        "dislike_count": ["live_dislike_count", "dislike_count"],
        "dislike_users": ["live_dislike_uv_by_room", "dislike_users"],
        "wechat_add_count": ["lp_screen_ad_biz_wechat_add_count", "wechat_add_count"],
        "wechat_add_cost": ["lp_screen_ad_biz_wechat_cost", "wechat_add_cost"],
        "form_submit_count": ["lp_screen_ad_form_count", "form_submit_count"],
        "form_submit_users": ["lp_screen_card_clue_uv", "form_submit_users"],
        "form_submit_cost": ["lp_screen_ad_form_cost", "form_submit_cost"],
        "exposure_enter_rate": ["lp_screen_live_exposure_enter_rate", "exposure_enter_rate"],
        "fans_view_ratio": ["lp_screen_live_fans_watch_ratio", "fans_view_ratio"],
        "scene_lead_conversion_rate": ["lp_screen_live_clue_convert_ratio", "scene_lead_conversion_rate"],
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


async def _scrape_home_live_card(context: BrowserContext) -> dict:
    """从主页直播卡片提取主播、标题、实时人数等稳定信息。"""
    page = await context.new_page()
    captured_api = []
    response_tasks = []

    async def on_response(resp):
        try:
            if "json" in resp.headers.get("content-type", ""):
                captured_api.append(await asyncio.wait_for(resp.json(), timeout=3))
        except Exception:
            pass

    page.on("response", lambda r: response_tasks.append(asyncio.create_task(on_response(r))))
    try:
        await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        body_text = await page.evaluate("document.body?.innerText || ''")
    except Exception:
        return {}
    finally:
        try:
            await page.close()
        except Exception as exc:
            if not _is_context_closed_message(exc):
                logger.debug("主页直播卡片页面关闭失败: %s", exc)
        await _drain_response_tasks(response_tasks)

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
        try:
            await page.close()
        except Exception as exc:
            if not _is_context_closed_message(exc):
                logger.debug("流地址页面关闭失败: %s", exc)


# ==================== 历史详情抓取 ====================


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
    validate_history: bool = True,
) -> dict:
    """从大屏页提取总览、趋势、回放流和评论。"""
    url = f"{LIVE_SCREEN_URL}?room_id={room_id}&fullscreen=0"
    page = None
    hits = {"overview": [], "data": [], "replay": []}
    response_tasks = []

    async def on_response(resp):
        try:
            if "json" not in resp.headers.get("content-type", ""):
                return
            if "/bff/statistic/live-screen/overview" in resp.url:
                hits["overview"].append(await resp.json())
            elif "/bff/statistic/live-screen/data" in resp.url:
                hits["data"].append(await resp.json())
            elif "/bff/statistic/live-screen/v3/get-live-replay" in resp.url:
                hits["replay"].append(await resp.json())
        except Exception:
            pass

    try:
        page = await context.new_page()
        page.on("response", lambda r: response_tasks.append(asyncio.create_task(on_response(r))))
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(6)
        try:
            clicked = await page.evaluate(
                """() => {
                  const node = [...document.querySelectorAll('*')]
                    .find(item => item.children.length === 0 && item.textContent?.trim() === '评论');
                  if (!node) return false;
                  node.click();
                  return true;
                }"""
            )
            if clicked:
                await asyncio.sleep(3)
        except Exception:
            pass

        body_text = await page.evaluate("document.body?.innerText || ''")
        await _drain_response_tasks(response_tasks)
        if validate_history and not _is_expected_history_session(body_text, session):
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

        # 企业主账号页面默认会脱敏显示主播名，点击小眼睛后才能读取本场真实主播。
        anchor_profile = await _reveal_session_anchor(page)

        overview_rows = []
        for payload in hits["overview"]:
            overview_rows.extend(((payload.get("data", {}) or {}).get("statRows")) or [])
        data_payload = {}
        for payload in hits["data"]:
            inner = payload.get("data", {}) or {}
            if isinstance(inner, dict):
                for key, value in inner.items():
                    if value not in (None, [], {}):
                        data_payload[key] = value
        trend_rows = data_payload.get("trend") or []
        profiles = _parse_watch_profiles(data_payload.get("watchProfile"))
        replay_url = next((
            ((payload.get("data", {}) or {}).get("replayUrl"))
            for payload in reversed(hits["replay"])
            if ((payload.get("data", {}) or {}).get("replayUrl"))
        ), None)
        comments, comments_authoritative = await _fetch_all_session_comments(page, room_id)
        if not comments_authoritative:
            comments = _parse_comments_from_live_screen_text(body_text, session.live_start_time)
        return {
            "overview": overview_rows[0] if overview_rows else {},
            "trend": trend_rows,
            "replay_url": replay_url,
            "comments": comments,
            "comments_authoritative": comments_authoritative,
            "anchor_profile": anchor_profile,
            "profiles": profiles,
        }
    except Exception as exc:
        return {
            "overview": {}, "trend": [], "replay_url": None, "comments": [],
            "anchor_profile": {}, "validation_failed": False,
            "error": str(exc),
        }
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass
            await _drain_response_tasks(response_tasks)


def _is_expected_history_session(body_text: str, session: LiveSession) -> bool:
    """校验当前详情页是否真的是目标场次，避免历史页面串场写错数据。"""
    from app.services.collector.utils import _is_expected_history_session as _check
    return _check(body_text, session.live_start_time, session.live_end_time)


async def _fetch_all_session_comments(page, room_id: str) -> tuple[list[dict], bool]:
    """通过评论接口分页读取整场评论，DOM 文本仅作为接口失败时的兜底。"""
    paging = 1000
    comments: list[dict] = []
    total = None
    authoritative = False
    page_no = 1
    while total is None or len(comments) < total:
        response = await _fetch_enterprise_post(
            page,
            "/bff/statistic/live-comment/comment-list",
            {"roomId": room_id, "page": str(page_no), "size": str(paging)},
        )
        data = response.get("data", {}) if isinstance(response, dict) else {}
        if not isinstance(data, dict):
            break
        authoritative = "comments" in data and "total" in data
        total = _safe_int(data.get("total")) or 0
        rows = data.get("comments") or []
        if not isinstance(rows, list) or not rows:
            break
        for item in rows:
            if not isinstance(item, dict) or not item.get("content"):
                continue
            profile = _parse_comment_user_profile(item)
            comments.append({
                **profile,
                "user_nickname": profile["user_nickname"] or "未知",
                "user_sec_uid": item.get("secUId") or None,
                "webcast_uid": item.get("webcastUid") or None,
                "comment_content": str(item.get("content")),
                "comment_time": _parse_comment_time(item.get("createTime")),
            })
        if len(rows) < paging:
            break
        page_no += 1
    return comments, authoritative


async def _fetch_enterprise_post(page, path: str, payload: dict, csrf_token: str = "") -> dict:
    """在企业后台页面内携带 CSRF 头发送 JSON 请求。"""
    result = await page.evaluate(
        """async ({path, payload, csrfToken}) => {
          const csrf = document.cookie.split(';').map(v => v.trim())
            .find(v => /^(feiyu_csrf_token|csrf_token|csrftoken|csrf-token)=/i.test(v))?.split('=').slice(1).join('=') || '';
          const resp = await fetch(path, {
            method: 'POST',
            credentials: 'include',
            headers: {'content-type': 'application/json;charset=utf-8', 'x-csrftoken': csrfToken || decodeURIComponent(csrf)},
            body: JSON.stringify(payload),
          });
          return await resp.json();
        }""",
        {"path": path, "payload": payload, "csrfToken": csrf_token},
    )
    return result if isinstance(result, dict) else {}


async def _reveal_session_anchor(page) -> dict:
    """点击直播大屏顶部小眼睛，读取企业主账号下本场主播。"""
    try:
        eye = page.locator('[data-log-name="显示账号"]').first
        try:
            await eye.click(timeout=3000, force=True)
        except Exception:
            # 企业后台的顶部层有时会拦截 Playwright 鼠标事件，直接触发 DOM click 更稳定。
            await page.evaluate("document.querySelector('[data-log-name=\\\"显示账号\\\"]')?.click()")
        await asyncio.sleep(0.5)
        return await page.evaluate(
            """() => {
              const inner = document.querySelector('#screen-account-select .leads-rimless-input-inner');
              const name = inner?.querySelector('span')?.textContent?.trim() || inner?.textContent?.trim() || '';
              return name && name !== '*******' ? {anchor_name: name, anchor_nickname: name} : {};
            }"""
        ) or {}
    except Exception as exc:
        logger.debug("读取本场主播资料失败: %s", exc)
        return {}


# ==================== 主播资料合并 ====================


def _merge_room_profile(primary: dict, fallback: dict) -> dict:
    """优先用房间级主播资料，缺失时回退到账号首页资料。"""
    merged = dict(primary or {})
    fallback = fallback or {}
    for key in ("anchor_name", "anchor_nickname", "anchor_avatar_url", "douyin_id", "douyin_uid"):
        if not merged.get(key) and fallback.get(key):
            merged[key] = fallback.get(key)
    return merged


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
