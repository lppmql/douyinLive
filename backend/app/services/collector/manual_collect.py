"""
刷新数据采集服务 - 采集所有主播及直播场次的完整数据

原则：
- room_id 只是访问大屏页的入口参数，不代表主播
- 所有场次信息（主播名称、直播标题、状态等）以页面实际数据为准
- 不硬编码/假设任何主播信息
"""
import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional
import re
from urllib.parse import urlencode, urlparse, parse_qs
from urllib.request import Request, urlopen
from sqlalchemy import func, text
from sqlalchemy.orm import Session
from playwright.async_api import BrowserContext

from app.core.logger import logger
from app.core.config import settings
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
HISTORY_DETAIL_TIMEOUT_SECONDS = 45
HISTORY_DETAIL_CONCURRENCY = 2
HISTORY_DETAIL_BATCH_SIZE = 20
ENTERPRISE_PAGE_SIZE = 100
ENTERPRISE_MAX_PAGES = 200


ProgressCallback = Callable[[str, int, int, int, str, Optional[dict[str, Any]]], None]


async def collect_all(
    db: Session,
    task_id: Optional[int] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> dict:
    """
    刷新采集所有房间、主播和直播场次的数据
    先访问大屏页，从页面实际数据中提取场次信息，再入库
    """
    def report(stage: str, percent: int, current: int, total: int, message: str, details=None):
        if progress_callback:
            progress_callback(stage, percent, current, total, message, details)

    report("prepare", 3, 0, 0, "正在查找可用采集账号")
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
    report("prepare", 8, 0, len(rooms), f"已加载 {len(rooms)} 个采集房间")

    if not rooms:
        return {
            "total_rooms": 0,
            "collected_rooms": 0,
            "message": "没有配置房间，请先在直播间管理添加 room_id",
            "results": [],
        }

    repaired_sessions, removed_comments = _repair_session_comment_integrity(db)
    if repaired_sessions or removed_comments:
        report(
            "data_repair",
            9,
            repaired_sessions,
            repaired_sessions,
            f"已合并 {repaired_sessions} 条重复场次、清理 {removed_comments} 条串场评论",
            {"merged_session_count": repaired_sessions, "removed_comment_count": removed_comments},
        )

    # 3. 获取持久化登录上下文（优先复用，自动验证 Cookie）
    report("login_check", 10, 0, len(rooms), "正在验证 Cookie 与浏览器指纹")
    context, is_valid, msg = await browser_manager.get_logged_in_context()
    if not is_valid:
        return {
            "total_rooms": len(rooms),
            "collected_rooms": 0,
            "message": msg or "登录已过期，请先在采集页面重新扫码登录",
            "results": [],
        }

    try:
        _phase_times = {}
        _phase_start = time.time()
        results = []
        for index, room in enumerate(rooms, start=1):
            report(
                "room_collection",
                10 + int(index / max(len(rooms), 1) * 25),
                index - 1,
                len(rooms),
                f"正在采集房间 {room.room_id_str}",
                {"room_id": room.room_id_str, "room_name": room.anchor_name or room.account_name},
            )
            try:
                result = await asyncio.wait_for(
                    _collect_room_data(db, context, room, task_id=task_id),
                    timeout=settings.ROOM_COLLECTION_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "房间采集超时: room_id=%s timeout=%ss",
                    room.room_id_str,
                    settings.ROOM_COLLECTION_TIMEOUT_SECONDS,
                )
                result = {
                    "room_id": room.room_id_str or str(room.id),
                    "anchor_name": room.anchor_name or "",
                    "is_live": False,
                    "error": f"采集超过 {settings.ROOM_COLLECTION_TIMEOUT_SECONDS} 秒",
                }

            # 登录检查和正式打开页面之间仍可能发生浏览器句柄失效，自动恢复一次即可。
            if _is_context_closed_message(result.get("error")):
                logger.warning("采集上下文已关闭，正在关闭浏览器并重启后重试: room_id=%s", room.room_id_str)
                # 关闭整个浏览器（包括 Playwright 连接），get_logged_in_context 会创建全新实例
                await browser_manager.close()
                context, recovered, recovery_message = await browser_manager.get_logged_in_context()
                if recovered and context:
                    try:
                        result = await asyncio.wait_for(
                            _collect_room_data(db, context, room, task_id=task_id),
                            timeout=settings.ROOM_COLLECTION_TIMEOUT_SECONDS,
                        )
                    except asyncio.TimeoutError:
                        result = {
                            "room_id": room.room_id_str or str(room.id),
                            "anchor_name": room.anchor_name or "",
                            "is_live": False,
                            "error": f"恢复后采集仍超过 {settings.ROOM_COLLECTION_TIMEOUT_SECONDS} 秒",
                        }
                else:
                    result["error"] = recovery_message or "浏览器上下文恢复失败，请重新扫码登录"
            results.append(result)
            report(
                "room_collection",
                10 + int(index / max(len(rooms), 1) * 25),
                index,
                len(rooms),
                f"房间采集进度 {index}/{len(rooms)}",
                result,
            )

        _phase_times["rooms"] = time.time() - _phase_start
        logger.info("[采集计时] 房间采集完成: %s间 耗时=%.1fs", len(results), _phase_times["rooms"])

        # 历史接口负责保证场次总量完整，企业接口负责补充主播映射。
        # 两者必须都执行，不能因为企业接口只返回部分主播而漏掉其他场次。
        report("enterprise_sync", 40, 0, 0, "正在同步全部企业主播及所属场次")
        _t_enterprise = time.time()
        enterprise_sync = await _sync_enterprise_anchor_sessions(db, context, rooms[0], task_id=task_id)
        # 企业主播映射时浏览器上下文可能已断开，检测到后重启浏览器重试一次
        if enterprise_sync.get("error") and _is_context_closed_message(enterprise_sync.get("error")):
            logger.warning("企业主播映射同步时浏览器上下文已关闭，正在重启浏览器后重试")
            await browser_manager.close()
            context, recovered, msg = await browser_manager.get_logged_in_context()
            if recovered and context:
                enterprise_sync = await _sync_enterprise_anchor_sessions(db, context, rooms[0], task_id=task_id)
        report(
            "enterprise_sync",
            60,
            enterprise_sync.get("profile_count", 0),
            enterprise_sync.get("discovered_session_count", 0),
            f"已发现 {enterprise_sync.get('anchor_count', 0)} 位主播、{enterprise_sync.get('discovered_session_count', 0)} 场直播",
            enterprise_sync,
        )
        _phase_times["enterprise"] = time.time() - _t_enterprise
        logger.info("[采集计时] 企业映射同步完成: %s位主播 耗时=%.1fs",
                     enterprise_sync.get("anchor_count", 0), _phase_times["enterprise"])

        report("history_sync", 65, 0, 0, "正在同步账号历史直播场次")
        _t_history = time.time()
        history_sync = _sync_history_sessions(db, account, rooms[0])
        report("history_sync", 75, history_sync, history_sync, f"历史场次同步完成，本次新增 {history_sync} 场")

        # 未映射只代表当前接口暂时没返回主播关系，不能在采集过程中删除真实场次。
        pruned_unmapped_count = 0
        report("detail_enrichment", 78, 0, 0, "正在检查全部场次的指标、评论和主播资料")

        def report_detail_progress(checked: int, total: int, enriched: int, failed: int) -> None:
            percent = 78 + int(checked / max(total, 1) * 16)
            report(
                "detail_enrichment",
                percent,
                checked,
                total,
                f"场次详情已处理 {checked}/{total}，补齐 {enriched} 场，失败 {failed} 场",
                {
                    "checked_count": checked,
                    "total_count": total,
                    "enriched_count": enriched,
                    "failed_count": failed,
                },
            )

        history_detail_progress = await _enrich_history_sessions(
            db,
            context,
            account,
            rooms[0],
            progress_callback=report_detail_progress,
        )
        _phase_times["details"] = time.time() - _t_history
        logger.info("[采集计时] 详情补齐完成: 检查=%s 补齐=%s 失败=%s 剩余=%s 耗时=%.1fs",
                     history_detail_progress.get("checked_count", 0),
                     history_detail_progress.get("enriched_count", 0),
                     history_detail_progress.get("failed_count", 0),
                     history_detail_progress.get("remaining_count", 0),
                     _phase_times["details"])
        report(
            "detail_enrichment",
            94,
            history_detail_progress["checked_count"],
            history_detail_progress["batch_size"],
            f"全部场次已检查，本次补齐 {history_detail_progress['enriched_count']} 场，失败 {history_detail_progress['failed_count']} 场",
            history_detail_progress,
        )

        # 采集完成后刷新持久化 Cookie（延长有效期）
        report("cookie_refresh", 97, 0, 0, "正在保存最新 Cookie 与浏览器指纹")
        await browser_manager.refresh_logged_in_state()

        collected = sum(1 for r in results if r.get("error") is None)
        final_result = {
            "total_rooms": len(rooms),
            "collected_rooms": collected,
            "history_synced_count": history_sync,
            "enterprise_anchor_count": enterprise_sync["anchor_count"],
            "enterprise_session_synced_count": enterprise_sync["session_count"],
            "enterprise_session_discovered_count": enterprise_sync.get("discovered_session_count", 0),
            "anchor_profile_synced_count": enterprise_sync["profile_count"],
            "unmapped_session_pruned_count": pruned_unmapped_count,
            "history_detail_synced_count": history_detail_progress["enriched_count"],
            "history_detail_checked_count": history_detail_progress["checked_count"],
            "history_detail_remaining_count": history_detail_progress["remaining_count"],
            "history_detail_batch_size": history_detail_progress["batch_size"],
            "history_detail_failed_count": history_detail_progress["failed_count"],
            "results": results,
        }
        total_time = time.time() - _phase_start
        logger.info("[采集计时] 📊 总耗时=%.1fs 明细: 房间=%.1fs 企业映射=%.1fs 详情补齐=%.1fs",
                     total_time,
                     _phase_times.get("rooms", 0),
                     _phase_times.get("enterprise", 0),
                     _phase_times.get("details", 0))
        report("completed", 100, collected, len(rooms), "刷新数据采集完成", final_result)
        return final_result
    finally:
        # 注意：不关闭 context！它被 browser_manager 持久化了
        pass


def _is_context_closed_message(value: Any) -> bool:
    """识别采集结果中的 Playwright 浏览器句柄关闭错误。"""
    text = str(value or "").lower()
    return any(marker in text for marker in (
        "target page, context or browser has been closed",
        "browsercontext.new_page",
        "browser.new_context",
    ))


def _prune_unmapped_sessions(db: Session, room: LiveRoom) -> int:
    """企业映射成功后删除无法安全归属主播的历史场次，避免污染场次列表。"""
    child_tables = (
        "high_intent_users",
        "analysis_reports",
        "leads",
        "live_audience_profiles",
        "asr_tasks",
        "transcript_full_texts",
        "transcript_segments",
        "knowledge_base",
        "stream_sources",
        "comments",
        "live_metrics",
    )
    session_ids = [
        row[0]
        for row in db.execute(
            text(
                "SELECT id FROM live_sessions "
                "WHERE room_id = :room_id AND (anchor_name IS NULL OR anchor_name = '')"
            ),
            {"room_id": room.id},
        ).all()
    ]
    if not session_ids:
        return 0

    placeholders = ",".join(f":session_id_{index}" for index in range(len(session_ids)))
    params = {f"session_id_{index}": value for index, value in enumerate(session_ids)}

    for table in child_tables:
        db.execute(text(f"DELETE FROM {table} WHERE session_id IN ({placeholders})"), params)
    db.execute(
        text(f"UPDATE scraper_tasks SET session_id = NULL WHERE session_id IN ({placeholders})"),
        params,
    )
    db.execute(text(f"DELETE FROM live_sessions WHERE id IN ({placeholders})"), params)
    db.add(
        ScraperLog(
            level="info",
            message=f"清理无主播归属历史场次: 删除={len(session_ids)}",
            raw_json={"room_id": room.room_id_str, "deleted_count": len(session_ids)},
        )
    )
    db.commit()
    logger.info("清理无主播归属历史场次: room_id=%s deleted=%s", room.room_id_str, len(session_ids))
    return len(session_ids)


async def _collect_room_data(
    db: Session,
    context: BrowserContext,
    room: LiveRoom,
    task_id: Optional[int] = None,
) -> dict:
    """采集单个房间的数据 — 以页面实际数据为准"""
    room_id = room.room_id_str
    # NOTE: anchor_name 不提前假设，从页面数据中提取

    logger.info(f"开始采集 room_id={room_id}")
    log_entry = ScraperLog(
        task_id=task_id,
        level="info",
        message=f"开始采集房间 {room_id}",
        raw_json={"stage": "room_collection", "event": "room_started", "room_id": room_id},
    )
    db.add(log_entry)
    db.commit()

    try:
        bff_page = None
        csrf_token = ""
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
        session = _get_or_create_session(db, room, room_id, session_title, is_live, now)
        _apply_room_profile(room, room_profile, anchor_name)
        if is_live and session.live_status != "live":
            session.live_status = "live"
            if not session.live_start_time:
                session.live_start_time = now

        session.dashboard_url = f"{LIVE_SCREEN_URL}?room_id={room_id}&fullscreen=0"

        # 4. 入库采集到的指标
        metrics_count = _save_metrics(db, session.id, page_data.get("metrics", []))
        profiles_count = _save_profiles(db, session.id, page_data.get("profiles", []))

        # 5. 确定用于 BFF API 的 room_id（优先用各主播的独立 room_id）
        ies_uid = room_profile.get("douyin_uid") or session_info.get("douyin_uid") or ""
        api_room_id = room_id
        if ies_uid:
            mapped = (
                db.query(LiveSession)
                .filter(
                    LiveSession.room_id == room.id,
                    LiveSession.douyin_uid == ies_uid,
                    LiveSession.dashboard_url.isnot(None),
                )
                .order_by(LiveSession.live_start_time.desc())
                .first()
            )
            if mapped:
                mapped_rid = _extract_room_id_from_dashboard_url(mapped.dashboard_url)
                if mapped_rid and mapped_rid != room_id:
                    api_room_id = mapped_rid
                    logger.info("[room_id选择] 使用主播独立 room_id: anchor=%s 企业room_id=%s → 主播room_id=%s (来自企业映射场次 %s)",
                                anchor_name, room_id, api_room_id, mapped.id)
                else:
                    logger.info("[room_id选择] 主播 %s 的映射场次无独立 room_id，继续使用企业 room_id=%s", anchor_name, room_id)
            else:
                logger.info("[room_id选择] 主播 %s 尚无企业映射记录（首次运行），使用企业 room_id=%s", anchor_name, room_id)
        else:
            logger.info("[room_id选择] 未获取到主播 iesUid，使用企业 room_id=%s", room_id)

        # 6. 打开 BFF 页面获取 CSRF Token，用于后续 API 直接调用
        bff_page_open_ok = False
        try:
            t0 = time.time()
            bff_page = await context.new_page()
            await bff_page.goto(
                f"{COMMENT_URL}?roomId={api_room_id}&fullscreen=0",
                wait_until="domcontentloaded", timeout=15000,
            )
            await asyncio.sleep(2)
            csrf_token = await bff_page.evaluate(
                "() => document.cookie.split(';').map(v => v.trim())"
                ".find(v => /^(feiyu_csrf_token|csrf_token|csrftoken|csrf-token)=/i.test(v))"
                "?.split('=').slice(1).join('=') || ''"
            )
            elapsed = time.time() - t0
            bff_page_open_ok = bool(csrf_token)
            if bff_page_open_ok:
                logger.info("[BFF页面] ✅ 已打开 room_id=%s 耗时=%.1fs CSRF长度=%s", api_room_id, elapsed, len(csrf_token))
            else:
                logger.warning("[BFF页面] ⚠️ 页面已打开但未获取到 CSRF Token room_id=%s 耗时=%.1fs，API调用将降级到页面抓取", api_room_id, elapsed)
        except Exception as exc:
            elapsed = time.time() - t0 if 't0' in dir() else 0
            logger.warning("[BFF页面] ❌ 打开失败 room_id=%s 耗时=%.1fs 错误=%s，将使用页面抓取降级", api_room_id, elapsed, exc)
            if bff_page:
                await bff_page.close()
                bff_page = None

        # 7. 用汇总指标更新场次记录
        sm = page_data.get("summary_metrics", {})
        if home_info.get("total_viewers") is not None:
            sm["total_viewers"] = home_info["total_viewers"]
        if home_info.get("realtime_online_count") is not None:
            sm["realtime_online_count"] = home_info["realtime_online_count"]
        if home_info.get("leads_count") is not None:
            sm["leads_count"] = home_info["leads_count"]
        if sm.get("total_viewers") is not None:
            session.total_viewers = sm["total_viewers"]
        if sm.get("viewed_count") is not None:
            session.viewed_count = sm["viewed_count"]
        if sm.get("avg_online_count") is not None:
            session.avg_online_count = sm["avg_online_count"]
        if sm.get("peak_online_count") is not None:
            session.peak_online_count = sm["peak_online_count"]
        if sm.get("realtime_online_count") is not None:
            session.realtime_online_count = sm["realtime_online_count"]
        if sm.get("avg_watch_seconds") is not None:
            session.avg_watch_seconds = float(sm["avg_watch_seconds"])
        if sm.get("fans_avg_watch_seconds") is not None:
            session.fans_avg_watch_seconds = float(sm["fans_avg_watch_seconds"])
        if sm.get("private_message_count") is not None:
            session.private_message_count = sm["private_message_count"]
        if sm.get("private_message_longterm_count") is not None:
            session.private_message_longterm_count = sm["private_message_longterm_count"]
        if sm.get("scene_leads_count") is not None:
            session.scene_leads_count = sm["scene_leads_count"]
        if sm.get("ad_cost") is not None:
            session.ad_cost = float(sm["ad_cost"])
        if sm.get("mini_windmill_click_count") is not None:
            session.mini_windmill_click_count = sm["mini_windmill_click_count"]
        if sm.get("mini_windmill_click_rate") is not None:
            session.mini_windmill_click_rate = float(sm["mini_windmill_click_rate"])
        if sm.get("card_click_count") is not None:
            session.card_click_count = sm["card_click_count"]
        if sm.get("card_click_rate") is not None:
            session.card_click_rate = float(sm["card_click_rate"])
        if sm.get("new_followers") is not None:
            session.new_followers = sm["new_followers"]
        if sm.get("follow_rate") is not None:
            session.follow_rate = float(sm["follow_rate"])
        if sm.get("share_count") is not None:
            session.share_count = sm["share_count"]
        if sm.get("share_users") is not None:
            session.share_users = sm["share_users"]
        if sm.get("like_count") is not None:
            session.like_count = sm["like_count"]
        if sm.get("like_users") is not None:
            session.like_users = sm["like_users"]
        if sm.get("leads_count") is not None:
            session.leads_count = sm["leads_count"]
        if sm.get("comments_count") is not None:
            session.comments_count = sm["comments_count"]
        if sm.get("comment_users") is not None:
            session.comment_users = sm["comment_users"]
        if sm.get("interaction_count") is not None:
            session.interaction_count = sm["interaction_count"]
        if sm.get("interaction_users") is not None:
            session.interaction_users = sm["interaction_users"]
        if sm.get("watch_count") is not None:
            session.watch_count = sm["watch_count"]
        if sm.get("watch_over_1m_count") is not None:
            session.watch_over_1m_count = sm["watch_over_1m_count"]
        if sm.get("fans_club_join_count") is not None:
            session.fans_club_join_count = sm["fans_club_join_count"]
        if sm.get("fans_club_join_rate") is not None:
            session.fans_club_join_rate = float(sm["fans_club_join_rate"])
        if sm.get("gift_count") is not None:
            session.gift_count = sm["gift_count"]
        if sm.get("gift_amount") is not None:
            session.gift_amount = float(sm["gift_amount"])
        if sm.get("dislike_count") is not None:
            session.dislike_count = sm["dislike_count"]
        if sm.get("dislike_users") is not None:
            session.dislike_users = sm["dislike_users"]
        if sm.get("wechat_add_count") is not None:
            session.wechat_add_count = sm["wechat_add_count"]
        if sm.get("wechat_add_cost") is not None:
            session.wechat_add_cost = float(sm["wechat_add_cost"])
        if sm.get("form_submit_count") is not None:
            session.form_submit_count = sm["form_submit_count"]
        if sm.get("form_submit_users") is not None:
            session.form_submit_users = sm["form_submit_users"]
        if sm.get("form_submit_cost") is not None:
            session.form_submit_cost = float(sm["form_submit_cost"])
        if sm.get("exposure_enter_rate") is not None:
            session.exposure_enter_rate = float(sm["exposure_enter_rate"])
        if sm.get("fans_view_ratio") is not None:
            session.fans_view_ratio = float(sm["fans_view_ratio"])
        if sm.get("scene_lead_conversion_rate") is not None:
            session.scene_lead_conversion_rate = float(sm["scene_lead_conversion_rate"])
        if sm.get("comment_rate") is not None:
            session.comment_rate = float(sm["comment_rate"])
        if sm.get("interaction_rate") is not None:
            session.interaction_rate = float(sm["interaction_rate"])

        # 8. 采集评论（优先用 BFF API）
        t_comments = time.time()
        comments_data = []
        comments_source = "页面抓取"
        try:
            comments_data = await _scrape_comments(context, api_room_id, ies_uid=ies_uid, bff_page=bff_page, csrf_token=csrf_token)
            if comments_data:
                comments_source = "BFF API"
        except Exception as exc:
            logger.warning("[评论] BFF API 采集异常，降级到页面抓取: %s", exc)
            comments_data = await _scrape_comments(context, room_id)
        comments_time = time.time() - t_comments

        # 如果用了主播独立 room_id，评论应保存到该主播对应的场次，而非企业场次
        comments_session_id = session.id
        if api_room_id != room_id and comments_data:
            anchor_s = (
                db.query(LiveSession)
                .filter(
                    LiveSession.room_id == room.id,
                    LiveSession.dashboard_url.like(f"%{api_room_id}%"),
                )
                .order_by(LiveSession.live_start_time.desc())
                .first()
            )
            if anchor_s:
                comments_session_id = anchor_s.id
                logger.info("[评论] 保存到主播独立场次 session_id=%s (原企业场次=%s) anchor=%s room_id=%s",
                            anchor_s.id, session.id, anchor_name, api_room_id)
            else:
                logger.info("[评论] 未找到主播 %s 的独立场次，暂存到企业场次 session_id=%s", anchor_name, session.id)
        comments_count = _save_comments(db, comments_session_id, comments_data)
        if comments_count and comments_session_id == session.id:
            session.comments_count = max(session.comments_count or 0, comments_count)
        logger.info("[评论] %s 采集: room_id=%s 获取=%s条 保存=%s条 耗时=%.1fs 目标场次=%s",
                    comments_source, api_room_id, len(comments_data), comments_count, comments_time, comments_session_id)

        # 9. 采集流地址（优先用回放 API）
        t_stream = time.time()
        stream_url = None
        stream_source = "页面抓取"
        try:
            stream_url = await _scrape_stream_url(context, api_room_id, bff_page=bff_page, csrf_token=csrf_token)
            if stream_url:
                stream_source = "BFF API回放"
        except Exception as exc:
            logger.warning("[流地址] BFF API 采集异常，降级到页面抓取: %s", exc)
            stream_url = await _scrape_stream_url(context, room_id)
        stream_time = time.time() - t_stream

        if stream_url:
            # 流地址也保存到正确的场次
            stream_session_id = session.id
            if api_room_id != room_id:
                anchor_s = (
                    db.query(LiveSession)
                    .filter(
                        LiveSession.room_id == room.id,
                        LiveSession.dashboard_url.like(f"%{api_room_id}%"),
                    )
                    .order_by(LiveSession.live_start_time.desc())
                    .first()
                )
                if anchor_s:
                    stream_session_id = anchor_s.id
            session_to_update = db.get(LiveSession, stream_session_id) or session
            session_to_update.stream_url = stream_url[:2000]
            _save_stream_source(db, stream_session_id, stream_url)
            logger.info("[流地址] %s 采集成功: room_id=%s 耗时=%.1fs 路径=%s... 目标场次=%s",
                        stream_source, api_room_id, stream_time, stream_url[:60], stream_session_id)
        else:
            logger.warning("[流地址] 未获取到流地址: room_id=%s 来源=%s 耗时=%.1fs", api_room_id, stream_source, stream_time)

        db.commit()

        logger.info(
            "[房间采集] ✅ 完成 room_id=%s 主播=%s 直播=%s "
            "指标=%s 评论=%s(%s条原始) 画像=%s 流地址=%s "
            "场次=%s api_room_id=%s",
            room_id, anchor_name, is_live,
            metrics_count, comments_count, len(comments_data) if comments_data else 0, profiles_count,
            "✅" if stream_url else "❌",
            session.id, api_room_id,
        )
        log_entry = ScraperLog(
            task_id=task_id,
            level="info",
            message=f"采集完成: {anchor_name}, 指标={metrics_count}, 评论={comments_count}",
            raw_json={
                "stage": "room_collection",
                "event": "room_completed",
                "room_id": room_id,
                "session_id": session.id,
                "anchor_name": session.anchor_name or anchor_name,
                "douyin_id": session.douyin_id or "",
                "is_live": is_live,
                "metrics_count": metrics_count,
                "comments_count": comments_count,
                "profiles_count": profiles_count,
                "stream_saved": bool(stream_url),
            },
        )
        db.add(log_entry)
        db.commit()

        return {
            "room_id": room_id,
            "anchor_name": session.anchor_name or anchor_name,
            "anchor_nickname": session.anchor_nickname or anchor_name,
            "douyin_id": session.douyin_id or "",
            "is_live": is_live,
            "metrics_count": metrics_count,
            "comments_count": comments_count,
            "profiles_count": profiles_count,
            "session_id": session.id,
        }

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        err_type = type(e).__name__
        # 生成可读的报错指引
        if "Timeout" in err_type or "timeout" in str(e).lower():
            fix_guide = "页面加载超时，可能是网络慢或页面元素变更，可重试或检查 leas.cluerich.com 是否可达"
        elif "BrowserContext" in str(e) or "browser" in str(e).lower():
            fix_guide = "浏览器上下文断开，系统会自动重启浏览器重试"
        elif "csrf" in str(e).lower() or "403" in str(e):
            fix_guide = "CSRF 校验失败，Cookie 可能已过期，请重新扫码登录"
        else:
            fix_guide = "未知异常，查看详细 traceback 定位问题"
        logger.error("[采集异常] ❌ room_id=%s 主播=%s 错误类型=%s 错误=%s 指引=%s",
                     room_id, anchor_name if 'anchor_name' in dir() else '?', err_type, e, fix_guide)
        logger.debug(tb)
        err_log = ScraperLog(
            task_id=task_id,
            level="error",
            message=f"采集失败 room_id={room_id}: {str(e)}",
            raw_json={
                "stage": "room_collection",
                "event": "room_failed",
                "room_id": room_id,
                "error_type": err_type,
                "error": str(e)[:2000],
                "fix_guide": fix_guide,
            },
        )
        db.add(err_log)
        db.commit()
        logger.warning("[采集异常] 已记录错误日志并返回，room_id=%s 指引=%s", room_id, fix_guide)
        return {"room_id": room_id, "error": f"[{err_type}] {e}", "fix_guide": fix_guide}
    finally:
        if bff_page:
            try:
                await bff_page.close()
            except Exception:
                pass


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
    page = None
    captured_api = []
    response_tasks = []
    try:
        page = await context.new_page()
    except Exception:
        logger.warning("创建大屏页面失败，浏览器上下文可能已断开: room_id=%s", room_id)
        return {"session_info": {}, "metrics": [], "profiles": [], "is_logged_in": False}

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
        if response_tasks:
            await asyncio.gather(*response_tasks, return_exceptions=True)
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


async def _scrape_comments(
    context: BrowserContext, room_id: str,
    ies_uid: Optional[str] = None,
    bff_page=None, csrf_token: str = "",
) -> list:
    """访问评论页，采集评论数据（优先用 BFF API，失败降级到页面抓取）"""
    # 如果有 BFF 页面和 CSRF Token，优先用 API
    api_result_total = None
    if bff_page and csrf_token and ies_uid:
        try:
            t0 = time.time()
            result = await _fetch_enterprise_post(
                bff_page,
                "/bff/statistic/live-comment/comment-list",
                {"roomId": room_id, "iesUid": ies_uid, "pageNum": 1, "pageSize": 50},
                csrf_token,
            )
            api_time = time.time() - t0
            data = result.get("data", {}) if isinstance(result, dict) else {}
            api_result_total = data.get("total") if isinstance(data, dict) else None
            if isinstance(data, dict):
                comment_list = data.get("comments") or data.get("list") or []
                resp_code = result.get("code") or result.get("error_code") or "ok"
                logger.info("[评论API] room_id=%s iesUid=%s 响应码=%s total=%s 返回列表=%s条 耗时=%.1fs",
                            room_id, ies_uid, resp_code, api_result_total, len(comment_list) if isinstance(comment_list, list) else 0, api_time)
                if comment_list and isinstance(comment_list, list):
                    comments = []
                    for c in comment_list:
                        if not isinstance(c, dict):
                            continue
                        nickname = c.get("user_nickname") or c.get("nickname") or c.get("nickName") or ""
                        content = c.get("comment_content") or c.get("content") or ""
                        if not content:
                            continue
                        comments.append({
                            "user_nickname": nickname,
                            "comment_content": content,
                            "comment_time": _parse_comment_time(c.get("comment_time") or c.get("createTime")),
                        })
                    if comments:
                        logger.info("[评论API] ✅ 采集成功 room_id=%s 有效评论=%s条 (原始=%s条 过滤空白=%s条)",
                                    room_id, len(comments), len(comment_list), len(comment_list) - len(comments))
                        return comments
                    else:
                        logger.warning("[评论API] ⚠️ 接口返回%s条但全部为空内容 room_id=%s", len(comment_list), room_id)
        except Exception as exc:
            logger.warning("[评论API] ❌ 请求异常 room_id=%s iesUid=%s 错误=[%s] %s，降级到页面抓取",
                           room_id, ies_uid, type(exc).__name__, exc)

    # 降级：页面抓取
    url = f"{COMMENT_URL}?roomId={room_id}&fullscreen=0"
    page = None
    captured_api = []
    response_tasks = []
    try:
        t0 = time.time()
        page = await context.new_page()
        logger.info("[评论] 降级到页面抓取: room_id=%s url=%s", room_id, url)
    except Exception:
        logger.warning("[评论] ❌ 创建页面失败，浏览器上下文可能已断开: room_id=%s", room_id)
        return []

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
        page_time = time.time() - t0
        logger.info("[评论] 页面抓取完成: room_id=%s 捕获API=%s个耗时=%.1fs", room_id, len(captured_api), page_time)
    except Exception as exc:
        logger.warning("[评论] 页面抓取异常 room_id=%s 耗时=%.1fs error=%s", room_id, time.time() - t0 if 't0' in dir() else 0, exc)
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
                nickname = c.get("user_nickname") or c.get("nickname") or c.get("nickName") or ""
                content = c.get("comment_content") or c.get("content") or ""
                if not content:
                    continue
                comments.append({
                    "user_nickname": nickname,
                    "comment_content": content,
                    "comment_time": _parse_comment_time(c.get("comment_time") or c.get("createTime")),
                })

    return comments


async def _scrape_home_live_card(context: BrowserContext) -> dict:
    """从主页直播卡片提取主播、标题、实时人数等稳定信息。"""
    page = None
    captured_api = []
    try:
        page = await context.new_page()
    except Exception:
        logger.warning("创建主页页面失败，浏览器上下文可能已断开")
        return {}

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
    # 平台接口限制每页最多 20 条，超过会返回 code=3 且没有 live_history。
    limit = 20
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
        try:
            with urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            # 历史接口偶发断开时不能阻断企业主播映射和逐场详情采集。
            logger.warning("历史场次接口暂时不可用，继续企业场次同步: %s", exc)
            db.add(ScraperLog(level="warning", message=f"历史场次同步降级: {str(exc)[:500]}"))
            db.commit()
            return synced
        if (payload or {}).get("code") not in (0, None):
            message = (payload or {}).get("msg") or "历史场次接口返回错误"
            logger.warning("历史场次接口返回错误，继续企业主播同步: %s", message)
            db.add(ScraperLog(level="warning", message=f"历史场次同步降级: {message}"))
            db.commit()
            return synced

        data = (payload or {}).get("data", {}) or {}
        history_rows = data.get("live_history") or []
        total = _safe_int(data.get("total_count")) or 0

        if not history_rows:
            break

        logger.info(
            "历史场次分页采集: page=%s, page_size=%s, total=%s, synced_before=%s",
            page_no,
            len(history_rows),
            total,
            synced,
        )

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


async def _sync_enterprise_anchor_sessions(
    db: Session,
    context: BrowserContext,
    room: LiveRoom,
    task_id: Optional[int] = None,
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
                start_time = _parse_epoch_dt(_first_value(item, "liveStartTime", "live_start_time", "startTime", "start_time"))
                end_time = _parse_epoch_dt(_first_value(item, "liveEndTime", "live_end_time", "endTime", "end_time"))
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
                session.live_status = "ended" if end_time else ("live" if _is_enterprise_live_status(live_status) else session.live_status or "finished")
                if changed:
                    profile_count += 1

        db.commit()
        db.add(
            ScraperLog(
                task_id=task_id,
                level="info",
                message=f"企业主播映射同步完成: 主播={len(unique_employees)}, 发现场次={discovered_session_count}, 新场次={session_count}, 更新={profile_count}",
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
        # 列出更新的主播清单
        anchor_lines = ", ".join([f"{p.get('iesName','?')}({len([s for s in unique_employees.values() if str(_first_value(p,'iesUid','ies_uid','uid','id'))==str(_first_value(s,'iesUid','ies_uid','uid','id'))])})" for p in unique_employees.values()][:5])
        logger.info(
            "[企业映射] ✅ 同步完成 anchors=%s discovered_sessions=%s new_sessions=%s profiles_updated=%s 主播=%s",
            len(unique_employees),
            discovered_session_count,
            session_count,
            profile_count,
            anchor_lines,
        )
        return {
            "anchor_count": len(unique_employees),
            "session_count": session_count,
            "discovered_session_count": discovered_session_count,
            "profile_count": profile_count,
        }
    except Exception as exc:
        db.rollback()
        db.add(ScraperLog(level="error", message=f"企业主播映射同步失败: {str(exc)[:500]}"))
        db.commit()
        logger.warning("企业主播映射同步失败: %s", exc)
        if _is_context_closed_error(exc):
            # 浏览器断开导致同步失败，返回 error 标记供外层触发浏览器重启
            return {"anchor_count": 0, "session_count": 0, "profile_count": 0, "error": str(exc)}
        return {"anchor_count": 0, "session_count": 0, "profile_count": 0}
    finally:
        if page:
            await page.close()


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


async def _fetch_live_replay(page, room_id: str, csrf_token: str = "") -> Optional[str]:
    """直接调用回放 API 获取 m3u8 流地址。"""
    try:
        result = await page.evaluate(
            """async ({path, params, csrfToken}) => {
              const csrf = document.cookie.split(';').map(v => v.trim())
                .find(v => /^(feiyu_csrf_token|csrf_token|csrftoken|csrf-token)=/i.test(v))?.split('=').slice(1).join('=') || '';
              const resp = await fetch(path + '?' + new URLSearchParams(params), {
                credentials: 'include',
                headers: {'x-csrftoken': csrfToken || decodeURIComponent(csrf)},
              });
              return await resp.json();
            }""",
            {"path": "/bff/statistic/live-screen/v3/get-live-replay",
             "params": {"roomId": room_id}, "csrfToken": csrf_token},
        )
        data = result.get("data", {}) if isinstance(result, dict) else {}
        replay_url = data.get("replayUrl") or data.get("replay_url") or None
        if replay_url:
            return str(replay_url)
    except Exception as exc:
        logger.debug("获取直播回放失败: room_id=%s error=%s", room_id, exc)
    return None


async def _fetch_living_status(page, csrf_token: str = "") -> dict:
    """直接获取当前直播状态。"""
    try:
        result = await page.evaluate(
            """async ({path, csrfToken}) => {
              const csrf = document.cookie.split(';').map(v => v.trim())
                .find(v => /^(feiyu_csrf_token|csrf_token|csrftoken|csrf-token)=/i.test(v))?.split('=').slice(1).join('=') || '';
              const resp = await fetch(path, {
                credentials: 'include',
                headers: {'x-csrftoken': csrfToken || decodeURIComponent(csrf)},
              });
              return await resp.json();
            }""",
            {"path": "/bff/statistic/live-screen/v3/get-living-status", "csrfToken": csrf_token},
        )
        data = result.get("data", {}) if isinstance(result, dict) else {}
        return data.get("roomInfo", {}) if isinstance(data, dict) else {}
    except Exception as exc:
        logger.debug("获取直播状态失败: %s", exc)
    return {}


async def _fetch_clue_detail(
    page, room_id: str, ies_uid: str, csrf_token: str = "",
    page_num: int = 1, page_size: int = 50,
) -> dict:
    """直接调用线索 API 获取留资数据。"""
    try:
        result = await _fetch_enterprise_post(
            page,
            "/bff/statistic/live-comment/clue-detail",
            {"roomId": room_id, "iesUid": ies_uid, "pageNum": page_num, "pageSize": page_size},
            csrf_token,
        )
        data = result.get("data", result) if isinstance(result, dict) else {}
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.debug("获取留资线索失败: room_id=%s error=%s", room_id, exc)
    return {}


def _is_enterprise_live_status(value) -> bool:
    """企业后台当前以 2 表示直播中；兼容旧接口曾使用的 1。"""
    return str(value).strip().lower() in {"1", "2", "live", "living"}


async def discover_enterprise_live_sessions(context: BrowserContext, room: LiveRoom) -> list[dict]:
    """轻量读取企业账号下全部主播的最新场次，返回正在直播的场次。"""
    root_room_id = str(room.room_id_str or "").strip()
    if not root_room_id:
        return []

    page = None
    try:
        page = await context.new_page()
    except Exception:
        logger.warning("创建企业主播发现页面失败，浏览器上下文可能已断开: room_id=%s", root_room_id)
        return []
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
                end_time = _parse_epoch_dt(_first_value(item, "liveEndTime", "live_end_time", "endTime", "end_time"))
                status = _first_value(item, "liveStatus", "live_status", "status")
                if not child_room_id or end_time or not _is_enterprise_live_status(status):
                    continue
                live_sessions.append({
                    "dashboard_url": f"{LIVE_SCREEN_URL}?room_id={child_room_id}&fullscreen=0",
                    "session_title": _first_value(item, "title", "roomTitle", "room_title", "sessionTitle"),
                    "live_start_time": _parse_epoch_dt(_first_value(item, "liveStartTime", "live_start_time", "startTime", "start_time")),
                    "anchor_name": _first_value(profile, "iesName", "ies_name", "nickname", "name"),
                    "anchor_nickname": _first_value(profile, "iesName", "ies_name", "nickname", "name"),
                    "anchor_avatar_url": _first_value(profile, "avatarUrl", "avatar_url", "avatar"),
                    "douyin_id": _first_value(profile, "iesUniqId", "iesId", "ies_id", "douyinId", "douyin_id"),
                    "douyin_uid": uid,
                })
        return live_sessions
    finally:
        await page.close()


def _first_value(data: dict, *keys: str):
    """返回第一个存在且非空的兼容字段值。"""
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


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


def _parse_epoch_dt(value) -> Optional[datetime]:
    """转换员工场次接口返回的 Unix 秒时间。"""
    if value in (None, "", 0, "0"):
        return None
    try:
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp)
    except (TypeError, ValueError, OverflowError):
        return None


async def _enrich_history_sessions(
    db: Session,
    context: BrowserContext,
    account: ScraperAccount,
    room: LiveRoom,
    progress_callback: Optional[Callable[[int, int, int, int], None]] = None,
) -> dict:
    """尝试补齐全部历史场次的大屏详情、回放流和评论。"""
    del account
    current_context = context
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

    metric_session_ids = {row[0] for row in db.query(LiveMetric.session_id).distinct().all()}
    comment_session_ids = {row[0] for row in db.query(Comment.session_id).distinct().all()}
    profile_session_ids = {row[0] for row in db.query(LiveAudienceProfile.session_id).distinct().all()}
    stream_session_ids = {row[0] for row in db.query(StreamSource.session_id).distinct().all()}
    asset_session_ids = metric_session_ids | comment_session_ids | profile_session_ids | stream_session_ids
    pending_sessions = [
        session for session in all_sessions
        if _needs_history_enrichment(session, session.id in asset_session_ids)
    ]
    repaired_false_complete = 0
    for session in pending_sessions:
        if session.detail_collection_status == "complete":
            session.detail_collection_status = "retryable"
            session.detail_collection_error = "此前未采到有效详情数据，已重新加入补齐队列"
            repaired_false_complete += 1
    if repaired_false_complete:
        db.commit()
        logger.warning("已修复 %s 场无数据但标记完整的历史场次", repaired_false_complete)
    # 先覆盖从未尝试过的场次，再重试暂时失败的场次，避免 retryable 阻塞全量首轮采集。
    pending_sessions.sort(
        key=lambda session: (
            session.detail_collection_status == "retryable",
            not bool(session.anchor_name),
            -(session.live_start_time.timestamp() if session.live_start_time else 0),
        )
    )
    target_sessions = pending_sessions[:HISTORY_DETAIL_BATCH_SIZE]
    enriched = 0
    checked = 0
    failed = 0
    semaphore = asyncio.Semaphore(HISTORY_DETAIL_CONCURRENCY)

    async def scrape_one(session: LiveSession):
        room_id = _extract_room_id_from_dashboard_url(session.dashboard_url)
        if not room_id:
            return session, None, "缺少场次 room_id"
        async with semaphore:
            try:
                detail = await asyncio.wait_for(
                    _scrape_history_session_detail(current_context, room_id, session),
                    timeout=HISTORY_DETAIL_TIMEOUT_SECONDS,
                )
                return session, detail, None
            except asyncio.TimeoutError:
                return session, None, "详情页采集超时，可在下次采集重试"
            except Exception as exc:
                return session, None, f"详情页采集失败: {str(exc)[:450]}"

    detail_tasks = [asyncio.create_task(scrape_one(session)) for session in target_sessions]
    for detail_task in asyncio.as_completed(detail_tasks):
        session, detail, error = await detail_task
        checked += 1
        if error:
            failed += 1
            session.detail_collection_status = "retryable"
            session.detail_collection_error = error
            db.commit()
            # 生成报错指引
            err_lower = error.lower()
            if "超时" in error or "timeout" in err_lower:
                fix = "该场次大屏页加载较慢，下次采集会自动重试。如持续超时，可手动确认页面是否正常打开"
            elif "csrf" in err_lower or "403" in error:
                fix = "CSRF 校验失败，Cookie 可能已过期，需重新扫码登录"
            elif "browser" in err_lower and "closed" in err_lower:
                fix = "浏览器上下文断开，系统将在下一轮自动恢复后重试"
            else:
                fix = "未知错误，可在前端页面查看该场次大屏页是否正常"
            logger.warning("[历史补齐] ❌ session_id=%s anchor=%s 场次=%s 错误=[%s] %s 指引=%s",
                           session.id, session.anchor_name or "?", session.session_title[:20] if session.session_title else "无标题",
                           type(error).__name__ if hasattr(error, '__name__') else 'Exception', str(error)[:200], fix)
            if progress_callback:
                progress_callback(checked, len(target_sessions), enriched, failed)
            continue

        if detail.get("validation_failed"):
            session.detail_collection_status = "unavailable"
            session.detail_collection_error = "平台详情页未回显该场次时间，无法安全确认主播归属"
            db.commit()
            failed += 1
            if progress_callback:
                progress_callback(checked, len(target_sessions), enriched, failed)
            continue

        overview = detail.get("overview", {})
        trend_rows = detail.get("trend", [])
        replay_url = detail.get("replay_url")
        comments_data = detail.get("comments", [])
        profiles = detail.get("profiles", [])
        anchor_profile = detail.get("anchor_profile", {}) or {}

        has_detail_data = bool(
            (overview.get("metrics", {}) if isinstance(overview, dict) else {})
            or trend_rows
            or comments_data
            or profiles
            or replay_url
        )
        if not has_detail_data:
            if not session.anchor_name:
                session.detail_collection_status = "unavailable"
                session.detail_collection_error = "平台未提供主播映射且详情接口为空，无法安全补齐"
            else:
                session.detail_collection_status = "retryable"
                session.detail_collection_error = "平台详情接口本次返回空数据，将在下次刷新时重试"
            db.commit()
            failed += 1
            if progress_callback:
                progress_callback(checked, len(target_sessions), enriched, failed)
            continue

        session.detail_collection_status = "complete"
        session.detail_collection_error = None

        changed = _apply_session_anchor_profile(session, anchor_profile)
        changed = _apply_overview_to_session(session, overview) or changed
        if replay_url and session.stream_url != replay_url:
            session.stream_url = replay_url[:2000]
            changed = True
        if replay_url:
            _save_stream_source(db, session.id, replay_url)

        metrics_count = _save_trend_metrics(db, session.id, trend_rows)
        comments_count = (
            _replace_session_comments(db, session.id, comments_data)
            if detail.get("comments_authoritative")
            else _save_comments(db, session.id, comments_data)
        )
        if detail.get("comments_authoritative"):
            session.comments_count = comments_count
            changed = True
        elif comments_count:
            session.comments_count = max(session.comments_count or 0, comments_count)
            changed = True

        if profiles:
            db.query(LiveAudienceProfile).filter(LiveAudienceProfile.session_id == session.id).delete()
            _save_profiles(db, session.id, profiles)

        if changed or metrics_count or comments_count:
            db.commit()
        enriched += 1
        if progress_callback:
            progress_callback(checked, len(target_sessions), enriched, failed)
        stream_status = "✅" if session.stream_url else "❌"
        has_profiles = "✅" if profiles else "❌"
        logger.info(
            "[历史补齐] ✅ session_id=%s anchor=%s metrics=%s comments=%s profiles=%s stream=%s 场次=%s",
            session.id,
            session.anchor_name or "未知主播",
            metrics_count,
            comments_count,
            has_profiles,
            stream_status,
            session.session_title[:30] if session.session_title else "无标题",
        )

    progress = {
        "enriched_count": enriched,
        "checked_count": checked,
        "remaining_count": max(0, len(pending_sessions) - checked),
        "batch_size": len(target_sessions),
        "failed_count": failed,
        "concurrency": HISTORY_DETAIL_CONCURRENCY,
    }
    db.add(
        ScraperLog(
            level="info",
            message=(
                f"历史详情刷新完成: 检查={checked}, 补齐={enriched}, "
                f"失败={failed}"
            ),
            raw_json=progress,
        )
    )
    db.commit()
    return progress


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
        if response_tasks:
            await asyncio.gather(*response_tasks, return_exceptions=True)
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
            "anchor_profile": {}, "validation_failed": False, "error": str(exc)[:500],
        }
    finally:
        if page:
            await page.close()


async def _fetch_all_session_comments(page, room_id: str) -> tuple[list[dict], bool]:
    """通过评论接口分页读取整场评论，DOM 文本仅作为接口失败时的兜底。"""
    page_size = 1000
    comments: list[dict] = []
    total = None
    authoritative = False
    page_no = 1
    while total is None or len(comments) < total:
        response = await _fetch_enterprise_post(
            page,
            "/bff/statistic/live-comment/comment-list",
            {"roomId": room_id, "page": str(page_no), "size": str(page_size)},
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
            comments.append({
                "user_nickname": item.get("nickName") or "未知",
                "user_sec_uid": item.get("secUId") or None,
                "webcast_uid": item.get("webcastUid") or None,
                "comment_content": str(item.get("content")),
                "comment_time": _parse_comment_time(item.get("createTime")),
            })
        if len(rows) < page_size:
            break
        page_no += 1
    return comments, authoritative


async def collect_live_session_snapshot(
    db: Session,
    context: BrowserContext,
    session: LiveSession,
) -> dict:
    """按刷新采集的完整结构更新一场正在直播的场次。"""
    room_id = _extract_room_id_from_dashboard_url(session.dashboard_url)
    if not room_id:
        raise RuntimeError("直播场次缺少 room_id，无法采集完整数据")

    detail = await _scrape_history_session_detail(
        context,
        room_id,
        session,
        validate_history=False,
    )
    if detail.get("error"):
        raise RuntimeError(f"实时完整快照页面采集失败: {detail['error']}")
    overview = detail.get("overview", {})
    trend_rows = detail.get("trend", [])
    comments_data = detail.get("comments", [])
    profiles = detail.get("profiles", [])
    anchor_profile = detail.get("anchor_profile", {}) or {}
    replay_url = detail.get("replay_url")

    changed = _apply_session_anchor_profile(session, anchor_profile)
    changed = _apply_overview_to_session(session, overview) or changed
    metrics_count = _save_trend_metrics(db, session.id, trend_rows)
    comments_count = (
        _replace_session_comments(db, session.id, comments_data)
        if detail.get("comments_authoritative")
        else _save_comments(db, session.id, comments_data)
    )
    profiles_count = 0
    if profiles:
        db.query(LiveAudienceProfile).filter(LiveAudienceProfile.session_id == session.id).delete()
        profiles_count = _save_profiles(db, session.id, profiles)
    if detail.get("comments_authoritative"):
        session.comments_count = comments_count
        changed = True
    elif comments_count:
        session.comments_count = max(session.comments_count or 0, comments_count)
        changed = True
    if replay_url and session.stream_url != replay_url:
        session.stream_url = replay_url[:2000]
        _save_stream_source(db, session.id, replay_url)
        changed = True
    if changed:
        db.commit()

    result = {
        "overview_field_count": len((overview.get("metrics", {}) or {})),
        "trend_row_count": len(trend_rows),
        "new_metric_count": metrics_count,
        "new_comment_count": comments_count,
        "profile_count": profiles_count,
        "stream_saved": bool(replay_url),
        "anchor_profile_updated": bool(anchor_profile),
    }
    logger.info("实时完整快照采集完成: session=%s result=%s", session.id, result)
    return result


def _parse_watch_profiles(raw_rows) -> list[dict]:
    """解析大屏 watchProfile 中以 JSON 字符串返回的实时用户画像。"""
    profiles = []
    field_prefix = "lp_screen_live_watch_profile_"
    for row in raw_rows or []:
        fields = row.get("fields", {}) if isinstance(row, dict) else {}
        for key, raw_value in fields.items():
            if not key.startswith(field_prefix):
                continue
            dimension_type = key.removeprefix(field_prefix)
            try:
                values = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
            except json.JSONDecodeError:
                continue
            if not isinstance(values, dict):
                continue
            for name, ratio in values.items():
                parsed_ratio = _safe_float(ratio)
                if parsed_ratio is None:
                    continue
                profiles.append({
                    "dimension_type": dimension_type,
                    "dimension_name": str(name),
                    "ratio": parsed_ratio,
                    "count": 0,
                })
    return profiles


def _is_context_closed_error(exc: Exception) -> bool:
    """识别 Playwright 上下文/页面已关闭错误。"""
    text = str(exc).lower()
    return "target page, context or browser has been closed" in text or "browsercontext.new_page" in text


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


async def _scrape_stream_url(
    context: BrowserContext, room_id: str,
    bff_page=None, csrf_token: str = "",
) -> Optional[str]:
    """采集 m3u8 流地址（优先用回放 API，失败降级到页面抓取）"""
    # 如果有 BFF 页面和 CSRF Token，优先用回放 API
    if bff_page and csrf_token:
        t0 = time.time()
        replay_url = await _fetch_live_replay(bff_page, room_id, csrf_token)
        api_time = time.time() - t0
        if replay_url:
            url_ext = replay_url.split('?')[0].split('.')[-1] if '.' in replay_url else '未知格式'
            logger.info("[流地址] ✅ BFF API回放 采集成功 room_id=%s 格式=%s 耗时=%.1fs 路径=%s...",
                        room_id, url_ext, api_time, replay_url[:60])
            return replay_url
        else:
            logger.info("[流地址] ⚠️ BFF API回放 未返回地址 room_id=%s 耗时=%.1fs，降级到页面抓取", room_id, api_time)

    # 降级：页面抓取
    url = f"{LIVE_SCREEN_URL}?room_id={room_id}&fullscreen=0"
    page = None
    m3u8_urls = []
    try:
        t0 = time.time()
        page = await context.new_page()
        logger.info("[流地址] 降级到页面抓取: room_id=%s url=%s", room_id, url)
    except Exception:
        logger.warning("[流地址] ❌ 创建页面失败，浏览器上下文可能已断开: room_id=%s", room_id)
        return None

    def on_request(req):
        if ".m3u8" in req.url:
            m3u8_urls.append(req.url)

    page.on("request", on_request)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        page_time = time.time() - t0
        if m3u8_urls:
            logger.info("[流地址] ✅ 页面抓取成功 room_id=%s 捕获m3u8=%s个 耗时=%.1fs 路径=%s...",
                        room_id, len(m3u8_urls), page_time, m3u8_urls[-1][:60])
            return m3u8_urls[-1]
        else:
            logger.warning("[流地址] ⚠️ 页面抓取未发现m3u8请求 room_id=%s 耗时=%.1fs", room_id, page_time)
            return None
    except Exception as exc:
        logger.warning("[流地址] ❌ 页面抓取异常 room_id=%s error=%s", room_id, exc)
        return None
    finally:
        await page.close()


# ==================== 数据入库 ====================


def _get_or_create_session(
    db: Session,
    room: LiveRoom,
    platform_room_id: str,
    session_title: str,
    is_live: bool,
    now: datetime,
) -> LiveSession:
    """严格按平台 roomId 获取场次，禁止把入口评论写入数据库最新场次。"""
    dashboard_url = f"{LIVE_SCREEN_URL}?room_id={platform_room_id}&fullscreen=0"
    session = (
        db.query(LiveSession)
        .filter(
            LiveSession.room_id == room.id,
            LiveSession.dashboard_url == dashboard_url,
        )
        .order_by(LiveSession.id.asc())
        .first()
    )

    if not session:
        session = LiveSession(
            room_id=room.id,
            dashboard_url=dashboard_url,
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


def _repair_session_comment_integrity(db: Session) -> tuple[int, int]:
    """合并相同平台 roomId 的重复场次，并清理直播时间区间外的串场评论。"""
    duplicate_urls = [
        row[0]
        for row in (
            db.query(LiveSession.dashboard_url)
            .filter(LiveSession.dashboard_url.isnot(None))
            .group_by(LiveSession.dashboard_url)
            .having(func.count(LiveSession.id) > 1)
            .all()
        )
    ]
    merged_count = 0
    generic_child_tables = (
        "high_intent_users", "analysis_reports", "leads", "asr_tasks",
        "transcript_full_texts", "transcript_segments", "knowledge_base", "scraper_tasks",
    )

    for dashboard_url in duplicate_urls:
        sessions = db.query(LiveSession).filter(LiveSession.dashboard_url == dashboard_url).all()

        def score(item: LiveSession) -> tuple[int, int]:
            asset_count = sum((
                db.query(Comment).filter(Comment.session_id == item.id).count(),
                db.query(LiveMetric).filter(LiveMetric.session_id == item.id).count(),
                db.query(LiveAudienceProfile).filter(LiveAudienceProfile.session_id == item.id).count(),
                db.query(StreamSource).filter(StreamSource.session_id == item.id).count(),
            ))
            summary_count = sum(bool(getattr(item, field, None)) for field in (
                "total_viewers", "peak_online_count", "comments_count", "interaction_count", "stream_url",
            ))
            return asset_count + summary_count * 10, item.id

        canonical = max(sessions, key=score)
        duplicate_ids = [item.id for item in sessions if item.id != canonical.id]
        if not duplicate_ids:
            continue

        # 先迁移全部强外键子记录，再去重，最后才能安全删除父场次。
        for model in (Comment, LiveMetric, LiveAudienceProfile, StreamSource):
            db.query(model).filter(model.session_id.in_(duplicate_ids)).update(
                {model.session_id: canonical.id}, synchronize_session=False
            )
        for table_name in generic_child_tables:
            db.execute(
                text(f"UPDATE `{table_name}` SET session_id = :canonical WHERE session_id IN ({','.join(map(str, duplicate_ids))})"),
                {"canonical": canonical.id},
            )
        db.flush()

        seen_comments = set()
        for row in db.query(Comment).filter(Comment.session_id == canonical.id).order_by(Comment.id):
            identity = _comment_identity(row.user_nickname, row.comment_content or "", row.comment_time, row.user_sec_uid)
            if identity in seen_comments:
                db.delete(row)
            else:
                seen_comments.add(identity)
        for model, identity_getter in (
            (LiveMetric, lambda row: row.metric_time),
            (LiveAudienceProfile, lambda row: (row.dimension_type, row.dimension_name)),
        ):
            seen = set()
            for row in db.query(model).filter(model.session_id == canonical.id).order_by(model.id):
                identity = identity_getter(row)
                if identity in seen:
                    db.delete(row)
                else:
                    seen.add(identity)
        db.flush()
        db.query(LiveSession).filter(LiveSession.id.in_(duplicate_ids)).delete(synchronize_session=False)
        merged_count += len(duplicate_ids)
        db.flush()
        canonical.comments_count = db.query(Comment).filter(Comment.session_id == canonical.id).count()

    db.flush()
    invalid_comments = []
    for comment, session in db.query(Comment, LiveSession).join(LiveSession, LiveSession.id == Comment.session_id):
        if not _comment_belongs_to_session(comment.comment_time, session):
            invalid_comments.append(comment)
    for comment in invalid_comments:
        db.delete(comment)
    db.commit()
    return merged_count, len(invalid_comments)


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
            clue_count=_safe_int(metrics.get("lp_screen_clue_uv")) or 0,
            windmill_click_count=_safe_int(metrics.get("lp_screen_live_icon_click_count")) or 0,
            card_click_count=_safe_int(metrics.get("lp_screen_live_clue_business_card_click_count")) or 0,
            wechat_add_count=_safe_int(metrics.get("lp_screen_ad_biz_wechat_add_count")) or 0,
            form_submit_count=_safe_int(metrics.get("lp_screen_ad_form_count")) or 0,
            form_submit_users=_safe_int(metrics.get("lp_screen_card_clue_uv")) or 0,
            cost_amount=_safe_float(metrics.get("lp_screen_live_stat_cost")) or 0,
            natural_traffic_count=_safe_int(metrics.get("lp_screen_live_watch_count_natural")) or 0,
            marketing_traffic_count=_safe_int(metrics.get("lp_screen_live_watch_count_ad")) or 0,
        )
        db.add(row)
        count += 1

    if count:
        db.commit()
    return count


def _save_stream_source(db: Session, session_id: int, stream_url: str) -> None:
    """保存可供后续 ASR 使用的流/回放地址，按场次和地址幂等。"""
    normalized = str(stream_url or "").strip()
    if not normalized:
        return
    exists = (
        db.query(StreamSource)
        .filter(StreamSource.session_id == session_id, StreamSource.m3u8_url == normalized[:2000])
        .first()
    )
    if exists:
        exists.status = "active"
        exists.fetched_at = datetime.utcnow()
        return
    source_type = "m3u8" if ".m3u8" in normalized.lower() else "replay"
    db.add(
        StreamSource(
            session_id=session_id,
            source_type=source_type,
            m3u8_url=normalized[:2000],
            status="active",
            fetched_at=datetime.utcnow(),
        )
    )


def _save_comments(db: Session, session_id: int, comments: list) -> int:
    """保存评论数据"""
    session = db.get(LiveSession, session_id)
    existing_pairs = {
        _comment_identity(row.user_nickname, row.comment_content or "", row.comment_time, row.user_sec_uid)
        for row in db.query(Comment).filter(Comment.session_id == session_id).all()
    }
    seen_pairs = set()
    count = 0
    for c in comments:
        content = c.get("comment_content", "").strip()
        comment_time = c.get("comment_time")
        if not content:
            continue
        if session and not _comment_belongs_to_session(comment_time, session):
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
        if pair in existing_pairs or pair in seen_pairs:
            continue
        seen_pairs.add(pair)

        if content:
            comment = Comment(
                session_id=session_id,
                user_nickname=nickname,
                user_sec_uid=c.get("user_sec_uid"),
                webcast_uid=c.get("webcast_uid"),
                comment_content=content,
                comment_time=comment_time or datetime.utcnow(),
            )
            db.add(comment)
            count += 1
    if count:
        db.commit()
    return count


def _replace_session_comments(db: Session, session_id: int, comments: list) -> int:
    """用平台完整评论快照替换旧的 DOM 残缺结果，并继承人工分析字段。"""
    old_rows = db.query(Comment).filter(Comment.session_id == session_id).all()
    session = db.get(LiveSession, session_id)
    annotations = {}
    for row in old_rows:
        key = ((row.user_nickname or "").strip(), (row.comment_content or "").strip())
        annotations.setdefault(key, (row.is_high_intent, row.sentiment, row.keywords))

    db.query(Comment).filter(Comment.session_id == session_id).delete(synchronize_session=False)
    seen = set()
    for item in comments:
        nickname = str(item.get("user_nickname") or "未知").strip()
        content = str(item.get("comment_content") or "").strip()
        comment_time = item.get("comment_time")
        if session and not _comment_belongs_to_session(comment_time, session):
            continue
        identity = _comment_identity(nickname, content, comment_time, item.get("user_sec_uid"))
        if not content or identity in seen:
            continue
        seen.add(identity)
        annotation = annotations.get((nickname, content), (0, None, None))
        db.add(Comment(
            session_id=session_id,
            user_nickname=nickname,
            user_sec_uid=item.get("user_sec_uid"),
            webcast_uid=item.get("webcast_uid"),
            comment_content=content,
            comment_time=comment_time or datetime.utcnow(),
            is_high_intent=annotation[0] or 0,
            sentiment=annotation[1],
            keywords=annotation[2],
        ))
    db.commit()
    return len(seen)


def _comment_belongs_to_session(comment_time: Optional[datetime], session: LiveSession) -> bool:
    """评论时间必须落在本场直播区间内，边界放宽两分钟兼容平台时间误差。"""
    if not comment_time or not session.live_start_time:
        return True
    tolerance = timedelta(minutes=2)
    if comment_time < session.live_start_time - tolerance:
        return False
    if session.live_end_time and comment_time > session.live_end_time + tolerance:
        return False
    return True


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


def _safe_float(val) -> Optional[float]:
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
        "viewed_count": "lp_screen_uv_with_preview",
        "avg_online_count": "lp_screen_live_avg_online_uv_by_room",
        "peak_online_count": "lp_screen_live_max_watch_uv_by_minute",
        "realtime_online_count": "lp_screen_live_user_realtime",
        "private_message_count": "lp_screen_msg_conversation_count",
        "private_message_longterm_count": "lp_screen_longterm_msg_clue_uv",
        "scene_leads_count": "lp_screen_clue_uv",
        "leads_count": "lp_screen_clue_uv",
        "mini_windmill_click_count": "lp_screen_live_icon_click_count",
        "card_click_count": "lp_screen_live_clue_business_card_click_count",
        "new_followers": "lp_screen_live_follow_uv",
        "comments_count": "lp_screen_live_comment_count",
        "share_count": "lp_screen_live_share_count",
        "share_users": "lp_screen_live_share_uv",
        "like_count": "lp_screen_live_like_count",
        "like_users": "lp_screen_live_like_uv",
        "comment_users": "lp_screen_live_comment_uv",
        "interaction_count": "lp_screen_live_interaction_count",
        "interaction_users": "lp_screen_live_interaction_uv_count",
        "watch_count": "lp_screen_live_watch_count",
        "watch_over_1m_count": "lp_screen_live_watch_gt_1min_count",
        "fans_club_join_count": "lp_screen_live_fans_club_join_uv",
        "gift_count": "lp_screen_live_gift_count",
        "dislike_count": "live_dislike_count",
        "dislike_users": "live_dislike_uv_by_room",
        "wechat_add_count": "lp_screen_ad_biz_wechat_add_count",
        "form_submit_count": "lp_screen_ad_form_count",
        "form_submit_users": "lp_screen_card_clue_uv",
    }
    for field, key in mapping.items():
        value = _safe_int(metrics.get(key))
        if value is not None and getattr(session, field) != value:
            setattr(session, field, value)
            changed = True

    float_mapping = {
        "avg_watch_seconds": "lp_screen_live_avg_watch_duration",
        "fans_avg_watch_seconds": "lp_screen_live_fans_avg_watch_duration",
        "ad_cost": "lp_screen_live_stat_cost",
        "exposure_enter_rate": "lp_screen_live_enter_ratio",
        "fans_view_ratio": "lp_screen_live_fans_watch_ratio",
        "scene_lead_conversion_rate": "lp_screen_live_clue_convert_ratio",
        "mini_windmill_click_rate": "lp_screen_live_icon_click_rate",
        "card_click_rate": "lp_screen_live_clue_business_card_click_rate",
        "follow_rate": "lp_screen_live_follow_ratio",
        "comment_rate": "lp_screen_live_comment_ratio",
        "interaction_rate": "lp_screen_live_interaction_ratio",
        "share_rate": "lp_screen_live_share_ratio",
        "like_rate": "lp_screen_live_like_ratio",
        "fans_club_join_rate": "lp_screen_live_fans_club_join_uv_ratio",
        "gift_amount": "lp_screen_live_gift_amount",
        "wechat_add_cost": "lp_screen_ad_biz_wechat_cost",
        "form_submit_cost": "lp_screen_ad_form_cost",
    }
    for field, key in float_mapping.items():
        raw = metrics.get(key)
        if raw is None:
            continue
        value = _safe_float(raw)
        if value is None:
            continue
        if getattr(session, field) != value:
            setattr(session, field, value)
            changed = True

    session.live_status = "ended" if session.live_end_time else session.live_status
    return changed


def _apply_session_anchor_profile(session: LiveSession, profile: dict) -> bool:
    """保存小眼睛展开后的本场主播资料，避免不同主播历史场次串号。"""
    changed = False
    for field in ("anchor_name", "anchor_nickname", "anchor_avatar_url", "douyin_id", "douyin_uid"):
        value = profile.get(field)
        if value and getattr(session, field) != value:
            setattr(session, field, str(value)[:500])
            changed = True
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


def _needs_history_enrichment(session: LiveSession, has_related_assets: bool = False) -> bool:
    """判断历史场次是否还需要继续补齐详情。"""
    if session.detail_collection_status in (None, "", "pending", "retryable"):
        return True
    if session.detail_collection_status != "complete":
        return False
    # 修复旧数据中的“假完整”：没有任何详情资产、核心指标或回放时应继续补齐。
    has_summary = any((
        session.total_viewers,
        session.viewed_count,
        session.peak_online_count,
        session.comments_count,
        session.interaction_count,
        session.private_message_count,
        session.new_followers,
    ))
    return not (has_related_assets or has_summary or session.stream_url)


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
