"""
刷新数据采集编排器 — 采集所有主播及直播场次的完整数据

原则：
- room_id 只是访问大屏页的入口参数，不代表主播
- 所有场次信息（主播名称、直播标题、状态等）以页面实际数据为准
- 不硬编码/假设任何主播信息

拆分后本文件只保留编排逻辑（~350 行），各领域逻辑分散到：
  room.py（页面抓取）、comments.py（评论）、metrics.py（指标/画像）、
  session.py（场次管理）、enterprise.py（企业同步）、history.py（历史补齐）、utils.py（工具函数）
"""
import asyncio
import re
from datetime import datetime
from typing import Any, Callable, Optional

from playwright.async_api import BrowserContext
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logger import logger
from app.models.asr_tasks import AsrTask
from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.models.scraper_accounts import ScraperAccount
from app.models.scraper_logs import ScraperLog

# 拆分后的领域模块
from app.services.asr.control import get_asr_runtime_status
from app.services.asr.queue import queue_auto_transcriptions
from app.services.collector.browser import browser_manager
from app.services.collector.comments import _save_comments, _scrape_comments
from app.services.collector.enterprise import _sync_enterprise_anchor_sessions as _do_enterprise_sync
from app.services.collector.history import (
    _enrich_history_sessions as _do_enrich_history,
    _sync_history_sessions as _do_history_sync,
)
from app.services.collector.metrics import _save_metrics, _save_profiles, _save_stream_source
from app.services.collector.room import (
    _apply_room_profile,
    _merge_room_profile,
    _scrape_home_live_card,
    _scrape_live_screen,
    _scrape_stream_url,
)
from app.services.collector.session import _get_or_create_session, _repair_session_comment_integrity
from app.services.collector.utils import _is_context_closed_message
from app.services.sync import sync_pending_complete_sessions

# ==================== 公共常量（本模块专用） ====================

LEADS_BASE = "https://leads.cluerich.com"
LIVE_SCREEN_URL = f"{LEADS_BASE}/pc/analysis/live-screen"
CONTEXT_RECOVERY_ATTEMPTS = 2
COLLECTOR_ERROR_MAX_LENGTH = 500

ProgressCallback = Callable[[str, int, int, int, str, Optional[dict[str, Any]]], None]


# ==================== 错误处理工具 ====================


def _sanitize_collector_error(value: Any, max_length: int = COLLECTOR_ERROR_MAX_LENGTH) -> str:
    """移除 Playwright 附带的浏览器底层日志，只保留可操作的业务错误。"""
    raw = str(value or "未知采集错误")
    compact = re.split(r"\bBrowser logs:\s*", raw, maxsplit=1, flags=re.IGNORECASE)[0]
    compact = re.sub(r"\s+", " ", compact).strip()
    if _is_context_closed_message(compact):
        compact = "浏览器进程意外退出（Target page, context or browser has been closed）"
    if len(compact) > max_length:
        compact = f"{compact[:max_length - 1]}…"
    return compact


def _record_room_failure(
    db: Session,
    task_id: Optional[int],
    room_id: str,
    error: Any,
    recovery_attempts: int = 0,
) -> None:
    """最终失败才写 error；自动恢复过程只记录 warn，避免误报。"""
    compact_error = _sanitize_collector_error(error)
    db.add(
        ScraperLog(
            task_id=task_id,
            level="error",
            message=f"采集失败 room_id={room_id}: {compact_error}",
            raw_json={
                "stage": "room_collection",
                "event": "room_failed",
                "room_id": room_id,
                "error": compact_error,
                "recovery_attempts": recovery_attempts,
            },
        )
    )
    db.commit()


def _sync_pending_dataease(limit: Optional[int]) -> dict:
    """使用线程专属数据库会话同步 DataEase；limit=None 表示同步全部待处理场次。"""
    sync_db = SessionLocal()
    try:
        return sync_pending_complete_sessions(sync_db, limit=limit)
    finally:
        sync_db.close()


# ==================== 向后兼容重导出 ====================

# 以下函数从子模块重导出，保持 scheduler.py 和 collector.py 的导入不变
from app.services.collector.enterprise import discover_enterprise_live_sessions  # noqa: E402, F811
from app.services.collector.history import collect_live_session_snapshot  # noqa: E402, F811


# ==================== 房间采集编排 ====================


async def _collect_room_data(
    db: Session,
    context: BrowserContext,
    room: LiveRoom,
    task_id: Optional[int] = None,
) -> dict:
    """采集单个房间的数据 — 以页面实际数据为准"""
    room_id = room.room_id_str

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

        # 5. 用汇总指标更新场次记录
        sm = page_data.get("summary_metrics", {})
        if home_info.get("total_viewers") is not None:
            sm["total_viewers"] = home_info["total_viewers"]
        if home_info.get("realtime_online_count") is not None:
            sm["realtime_online_count"] = home_info["realtime_online_count"]
        if home_info.get("leads_count") is not None:
            sm["leads_count"] = home_info["leads_count"]
        _apply_summary_metrics_to_session(session, sm)

        # 6. 采集评论
        comments_data = await _scrape_comments(context, room_id)
        comments_count = _save_comments(db, session.id, comments_data)
        if comments_count:
            session.comments_count = max(session.comments_count or 0, comments_count)

        # 7. 采集流地址
        stream_url = await _scrape_stream_url(context, room_id)
        if stream_url:
            session.stream_url = stream_url[:2000]
            _save_stream_source(db, session.id, stream_url)

        db.commit()

        logger.info(
            f"采集完成 room_id={room_id}, "
            f"主播={anchor_name}, 直播={is_live}, "
            f"指标={metrics_count}, 评论={comments_count}, 画像={profiles_count}"
        )
        db.add(
            ScraperLog(
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
        )
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
        compact_error = _sanitize_collector_error(e)
        recoverable = _is_context_closed_message(e)
        if recoverable:
            logger.warning("房间采集浏览器中断，等待自动恢复: room_id=%s error=%s", room_id, compact_error)
            db.add(
                ScraperLog(
                    task_id=task_id,
                    level="warn",
                    message=f"房间 {room_id} 的浏览器连接中断，正在自动恢复",
                    raw_json={
                        "stage": "room_collection",
                        "event": "room_recovery_pending",
                        "room_id": room_id,
                        "error_type": type(e).__name__,
                        "error": compact_error,
                    },
                )
            )
            db.commit()
        else:
            logger.exception("采集 room_id=%s 失败: %s", room_id, compact_error)
            _record_room_failure(db, task_id, room_id, compact_error)
        return {
            "room_id": room_id,
            "error": compact_error,
            "recoverable": recoverable,
            "failure_logged": not recoverable,
        }


def _apply_summary_metrics_to_session(session: LiveSession, sm: dict) -> None:
    """把采集到的汇总指标写入 LiveSession 字段。"""
    # 整数类型字段
    int_fields = [
        "total_viewers", "viewed_count", "avg_online_count", "peak_online_count",
        "realtime_online_count", "private_message_count", "private_message_longterm_count",
        "scene_leads_count", "mini_windmill_click_count", "card_click_count",
        "new_followers", "share_count", "share_users", "like_count", "like_users",
        "leads_count", "comments_count", "comment_users", "interaction_count",
        "interaction_users", "watch_count", "watch_over_1m_count", "fans_club_join_count",
        "gift_count", "dislike_count", "dislike_users", "wechat_add_count",
        "form_submit_count", "form_submit_users",
    ]
    # 浮点数类型字段
    float_fields = [
        "avg_watch_seconds", "fans_avg_watch_seconds", "ad_cost",
        "mini_windmill_click_rate", "card_click_rate", "follow_rate",
        "share_rate", "exposure_enter_rate", "fans_view_ratio",
        "scene_lead_conversion_rate", "comment_rate", "interaction_rate",
        "gift_amount", "wechat_add_cost", "form_submit_cost",
        "fans_club_join_rate",
    ]

    for field in int_fields:
        val = sm.get(field)
        if val is not None:
            setattr(session, field, val)

    for field in float_fields:
        val = sm.get(field)
        if val is not None:
            setattr(session, field, float(val))


# ==================== 未映射场次清理 ====================


def _prune_unmapped_sessions(db: Session, room: LiveRoom) -> int:
    """企业映射成功后删除无法安全归属主播的历史场次，避免污染场次列表。"""
    child_tables = (
        "high_intent_users", "analysis_reports", "leads",
        "live_audience_profiles", "asr_tasks",
        "transcript_full_texts", "transcript_segments",
        "knowledge_base", "stream_sources", "comments", "live_metrics",
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


# ==================== 主编排入口 ====================


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
    # 1. 获取已登录账号
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

    # 3. 获取持久化登录上下文
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

            # Chromium 异常退出时从保存的 Cookie 与指纹恢复
            recovery_attempt = 0
            while _is_context_closed_message(result.get("error")) and recovery_attempt < CONTEXT_RECOVERY_ATTEMPTS:
                recovery_attempt += 1
                logger.warning(
                    "采集浏览器异常退出，正在恢复并重试: room_id=%s attempt=%s/%s",
                    room.room_id_str,
                    recovery_attempt,
                    CONTEXT_RECOVERY_ATTEMPTS,
                )
                browser_manager.invalidate_logged_in_context(context)
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
                    break

            if recovery_attempt and not result.get("error"):
                db.add(
                    ScraperLog(
                        task_id=task_id,
                        level="info",
                        message=f"浏览器已自动恢复，房间 {room.room_id_str} 重试采集成功",
                        raw_json={
                            "stage": "room_collection",
                            "event": "room_recovered",
                            "room_id": room.room_id_str,
                            "recovery_attempts": recovery_attempt,
                        },
                    )
                )
                db.commit()
            elif not result.get("failure_logged") and result.get("error") and (
                result.get("recoverable") or recovery_attempt or "采集超过" in str(result.get("error"))
            ):
                _record_room_failure(
                    db, task_id, room.room_id_str or str(room.id), result["error"], recovery_attempt,
                )
            results.append(result)
            report(
                "room_collection",
                10 + int(index / max(len(rooms), 1) * 25),
                index,
                len(rooms),
                f"房间采集进度 {index}/{len(rooms)}",
                result,
            )

        # 历史接口负责保证场次总量完整，企业接口负责补充主播映射。
        report("enterprise_sync", 40, 0, 0, "正在同步全部企业主播及所属场次")
        enterprise_sync = await _do_enterprise_sync(
            db, context, rooms[0], task_id=task_id, sanitize_error=_sanitize_collector_error,
        )
        enterprise_recovery_attempt = 0
        while (
            _is_context_closed_message(enterprise_sync.get("error"))
            and enterprise_recovery_attempt < CONTEXT_RECOVERY_ATTEMPTS
        ):
            enterprise_recovery_attempt += 1
            browser_manager.invalidate_logged_in_context(context)
            context, recovered, recovery_message = await browser_manager.get_logged_in_context()
            if not recovered or not context:
                enterprise_sync["error"] = recovery_message or "浏览器上下文恢复失败，请重新扫码登录"
                break
            enterprise_sync = await _do_enterprise_sync(
                db, context, rooms[0], task_id=task_id, sanitize_error=_sanitize_collector_error,
            )
        if enterprise_sync.get("error"):
            compact_error = _sanitize_collector_error(enterprise_sync["error"])
            db.add(
                ScraperLog(
                    task_id=task_id,
                    level="error",
                    message=f"企业主播映射最终失败: {compact_error}",
                    raw_json={
                        "stage": "enterprise_sync",
                        "event": "enterprise_sync_failed",
                        "error": compact_error,
                        "recovery_attempts": enterprise_recovery_attempt,
                    },
                )
            )
            db.commit()
        report(
            "enterprise_sync",
            60,
            enterprise_sync.get("profile_count", 0),
            enterprise_sync.get("discovered_session_count", 0),
            f"已发现 {enterprise_sync.get('anchor_count', 0)} 位主播、"
            f"{enterprise_sync.get('discovered_session_count', 0)} 场直播",
            enterprise_sync,
        )
        report("history_sync", 65, 0, 0, "正在同步账号历史直播场次")
        history_sync = await _do_history_sync(db, account, rooms[0])
        report("history_sync", 75, history_sync, history_sync, f"历史场次同步完成，本次新增 {history_sync} 场")

        # 未映射只代表当前接口暂时没返回主播关系，不能在采集过程中删除真实场次。
        pruned_unmapped_count = 0
        report("detail_enrichment", 78, 0, 0, "正在检查全部场次的指标、评论和主播资料")

        def report_detail_progress(checked: int, total: int, enriched: int, failed: int) -> None:
            percent = 78 + int(checked / max(total, 1) * 16)
            remaining = max(0, total - checked)
            report(
                "detail_enrichment",
                percent,
                checked,
                total,
                f"场次详情已处理 {checked}/{total}，补齐 {enriched} 场，失败 {failed} 场，剩余 {remaining} 场",
                {
                    "checked_count": checked, "total_count": total,
                    "enriched_count": enriched, "failed_count": failed, "remaining_count": remaining,
                },
            )

        history_detail_progress = await _do_enrich_history(
            db, context, account, rooms[0],
            progress_callback=report_detail_progress,
            sanitize_error=_sanitize_collector_error,
        )
        report(
            "detail_enrichment",
            94,
            history_detail_progress["checked_count"],
            history_detail_progress["batch_size"],
            f"全部场次已检查，本次补齐 {history_detail_progress['enriched_count']} 场，"
            f"失败 {history_detail_progress['failed_count']} 场",
            history_detail_progress,
        )

        # 采集完成后刷新持久化 Cookie
        report("cookie_refresh", 97, 0, 0, "正在保存最新 Cookie 与浏览器指纹")
        await browser_manager.refresh_logged_in_state()

        report("dataease_sync", 98, 0, 0, "正在增量同步 DataEase 分析宽表")
        db.commit()
        dataease_sync = await asyncio.to_thread(_sync_pending_dataease, None)
        db.expire_all()

        report("asr_queue", 99, 0, settings.ASR_MAX_QUEUED, "正在按安全容量补充话术转写队列")
        asr_runtime = await asyncio.to_thread(get_asr_runtime_status)
        asr_queue = (
            queue_auto_transcriptions(db, limit=settings.ASR_MAX_QUEUED)
            if asr_runtime["enabled"]
            else {"created_count": 0, "active_count": 0, "capacity": settings.ASR_MAX_QUEUED, "session_ids": []}
        )
        postprocess_counts = {
            status: db.query(AsrTask).filter(
                AsrTask.status == "completed",
                AsrTask.postprocess_status == status,
            ).count()
            for status in ("pending", "processing", "completed", "failed")
        }
        report(
            "post_collection",
            99,
            postprocess_counts["completed"],
            sum(postprocess_counts.values()),
            (
                "话术转写完成后将自动生成 AI 复盘并同步知识库："
                f"待处理 {postprocess_counts['pending']}，处理中 {postprocess_counts['processing']}，"
                f"已完成 {postprocess_counts['completed']}，失败 {postprocess_counts['failed']}"
            ),
            postprocess_counts,
        )

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
            "dataease_synced_count": dataease_sync["synced_count"],
            "dataease_failed_count": dataease_sync["failed_count"],
            "asr_queued_count": asr_queue["created_count"],
            "asr_active_count": asr_queue["active_count"],
            "asr_queue_capacity": asr_queue["capacity"],
            "postprocess_pending_count": postprocess_counts["pending"],
            "postprocess_processing_count": postprocess_counts["processing"],
            "postprocess_completed_count": postprocess_counts["completed"],
            "postprocess_failed_count": postprocess_counts["failed"],
            "results": results,
        }
        report("completed", 100, collected, len(rooms), "刷新数据采集完成", final_result)
        return final_result
    finally:
        # 注意：不关闭 context！它被 browser_manager 持久化了
        pass
