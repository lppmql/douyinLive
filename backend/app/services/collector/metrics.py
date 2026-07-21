"""
指标和画像持久化 — 从 manual_collect.py 提取

负责：实时指标入库、趋势指标入库、观众画像入库、摘要字段映射写入、流地址保存
"""
import json
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.live_audience_profiles import LiveAudienceProfile
from app.models.live_metrics import LiveMetric
from app.models.live_sessions import LiveSession
from app.models.stream_sources import StreamSource
from app.services.collector.utils import _safe_float, _safe_int


def _save_metrics(db: Session, session_id: int, metrics: list) -> int:
    """保存实时指标数据。"""
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
        metrics_data = item.get("metrics", {}) or {}
        stat_time_minute = dimensions.get("stat_time_minute")
        if not stat_time_minute:
            continue
        metric_time = datetime.fromtimestamp(int(stat_time_minute) / 1000)
        if metric_time in existing_times:
            continue

        row = LiveMetric(
            session_id=session_id,
            metric_time=metric_time,
            exposure_count=_safe_int(metrics_data.get("lp_screen_live_show_count")) or 0,
            online_count=_safe_int(metrics_data.get("lp_screen_live_max_watch_uv_by_minute")) or 0,
            enter_count=_safe_int(metrics_data.get("lp_screen_live_watch_uv_by_minute")) or 0,
            enter_fans_count=_safe_int(metrics_data.get("lp_screen_live_fans_watch_uv_by_minute")) or 0,
            leave_count=_safe_int(metrics_data.get("lp_screen_live_leave_uv_by_minute")) or 0,
            like_count=_safe_int(metrics_data.get("lp_screen_live_like_count")) or 0,
            comment_count=_safe_int(metrics_data.get("lp_screen_live_comment_count")) or 0,
            follow_count=_safe_int(metrics_data.get("lp_screen_live_follow_count")) or 0,
            clue_count=_safe_int(metrics_data.get("lp_screen_clue_uv")) or 0,
            windmill_click_count=_safe_int(metrics_data.get("lp_screen_live_icon_click_count")) or 0,
            card_click_count=_safe_int(metrics_data.get("lp_screen_live_clue_business_card_click_count")) or 0,
            wechat_add_count=_safe_int(metrics_data.get("lp_screen_ad_biz_wechat_add_count")) or 0,
            form_submit_count=_safe_int(metrics_data.get("lp_screen_ad_form_count")) or 0,
            form_submit_users=_safe_int(metrics_data.get("lp_screen_card_clue_uv")) or 0,
            cost_amount=_safe_float(metrics_data.get("lp_screen_live_stat_cost")) or 0,
            natural_traffic_count=_safe_int(metrics_data.get("lp_screen_live_watch_count_natural")) or 0,
            marketing_traffic_count=_safe_int(metrics_data.get("lp_screen_live_watch_count_ad")) or 0,
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


def _save_profiles(db: Session, session_id: int, profiles: list) -> int:
    """保存观众画像数据。"""
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


def _apply_overview_to_session(session: LiveSession, overview_row: dict) -> bool:
    """把大屏 overview API 返回的指标映射写入 LiveSession 字段。"""
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
