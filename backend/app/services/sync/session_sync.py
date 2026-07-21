"""
场次汇总同步 — 同步 3 张表：
1. de_live_session_anchor_summary — 场次汇总宽表
2. de_anchor_realtime_metrics — 分钟级实时指标
3. de_anchor_conversion_funnel — 转化漏斗
"""
from datetime import datetime
from sqlalchemy import text, func
from app.core.logger import logger
from app.models.live_sessions import LiveSession
from app.models.live_rooms import LiveRoom
from app.models.leads import Lead
from app.models.live_metrics import LiveMetric
from app.models.de_tables import (
    DeAnchorRealtimeMetrics,
    DeAnchorConversionFunnel,
)


def sync_session_summary(db, session_id: int):
    """
    同步场次汇总宽表（de_live_session_anchor_summary）
    使用 INSERT ... ON DUPLICATE KEY UPDATE 幂等写入
    """
    session = db.query(LiveSession).get(session_id)
    if not session:
        logger.warning(f"session {session_id} 不存在，跳过")
        return

    room = db.query(LiveRoom).get(session.room_id) if session.room_id else None

    # 聚合有效留资
    valid_leads = db.query(func.count(Lead.id)).filter(
        Lead.session_id == session_id,
        Lead.is_valid == 1,
    ).scalar() or 0

    total_leads = session.leads_count or 0
    lead_valid_rate = (valid_leads / total_leads) if total_leads > 0 else 0
    ad_cost = float(session.ad_cost or 0)
    lead_cost = (ad_cost / valid_leads) if valid_leads > 0 else 0

    sql = text("""
        INSERT INTO de_live_session_anchor_summary
        (stat_date, session_id, room_id, anchor_name, team_name,
         session_title, live_start_time, live_end_time, live_duration_seconds,
         total_viewers, avg_watch_seconds, peak_online_count, realtime_online_count,
         ad_cost, new_followers, comments_count, leads_count,
         valid_leads_count, lead_valid_rate, lead_cost,
         exposure_enter_rate, share_rate, like_rate, comment_rate, interaction_rate,
         natural_traffic_ratio, marketing_traffic_ratio, other_traffic_ratio,
         live_exposure_users, live_enter_users, card_click_users,
         private_message_count, scene_leads_count, mini_windmill_click_count,
         created_at, updated_at)
        VALUES (:stat_date, :session_id, :room_id, :anchor_name, :team_name,
                :session_title, :live_start_time, :live_end_time, :live_duration_seconds,
                :total_viewers, :avg_watch_seconds, :peak_online_count, :realtime_online_count,
                :ad_cost, :new_followers, :comments_count, :leads_count,
                :valid_leads_count, :lead_valid_rate, :lead_cost,
                :exposure_enter_rate, :share_rate, :like_rate, :comment_rate, :interaction_rate,
                :natural_traffic_ratio, :marketing_traffic_ratio, :other_traffic_ratio,
                :live_exposure_users, :live_enter_users, :card_click_users,
                :private_message_count, :scene_leads_count, :mini_windmill_click_count,
                :created_at, :updated_at)
        ON DUPLICATE KEY UPDATE
            stat_date = VALUES(stat_date), room_id = VALUES(room_id),
            anchor_name = VALUES(anchor_name), team_name = VALUES(team_name),
            session_title = VALUES(session_title),
            live_start_time = VALUES(live_start_time), live_end_time = VALUES(live_end_time),
            live_duration_seconds = VALUES(live_duration_seconds),
            total_viewers = VALUES(total_viewers), avg_watch_seconds = VALUES(avg_watch_seconds),
            peak_online_count = VALUES(peak_online_count), realtime_online_count = VALUES(realtime_online_count),
            ad_cost = VALUES(ad_cost), new_followers = VALUES(new_followers),
            comments_count = VALUES(comments_count), leads_count = VALUES(leads_count),
            valid_leads_count = VALUES(valid_leads_count), lead_valid_rate = VALUES(lead_valid_rate),
            lead_cost = VALUES(lead_cost),
            exposure_enter_rate = VALUES(exposure_enter_rate), share_rate = VALUES(share_rate),
            like_rate = VALUES(like_rate), comment_rate = VALUES(comment_rate),
            interaction_rate = VALUES(interaction_rate),
            natural_traffic_ratio = VALUES(natural_traffic_ratio),
            marketing_traffic_ratio = VALUES(marketing_traffic_ratio),
            other_traffic_ratio = VALUES(other_traffic_ratio),
            live_exposure_users = VALUES(live_exposure_users), live_enter_users = VALUES(live_enter_users),
            card_click_users = VALUES(card_click_users),
            private_message_count = VALUES(private_message_count),
            scene_leads_count = VALUES(scene_leads_count),
            mini_windmill_click_count = VALUES(mini_windmill_click_count),
            updated_at = VALUES(updated_at)
    """)

    now = datetime.utcnow()
    start = session.live_start_time
    stat_date_val = start.date() if start else None

    db.execute(sql, {
        "stat_date": stat_date_val,
        "session_id": session_id,
        "room_id": session.room_id,
        "anchor_name": session.anchor_name or (room.anchor_name if room else None),
        "team_name": room.team_name if room else None,
        "session_title": session.session_title,
        "live_start_time": session.live_start_time,
        "live_end_time": session.live_end_time,
        "live_duration_seconds": session.live_duration_seconds or 0,
        "total_viewers": session.total_viewers or 0,
        "avg_watch_seconds": float(session.avg_watch_seconds or 0),
        "peak_online_count": session.peak_online_count or 0,
        "realtime_online_count": session.realtime_online_count or 0,
        "ad_cost": float(session.ad_cost or 0),
        "new_followers": session.new_followers or 0,
        "comments_count": session.comments_count or 0,
        "leads_count": total_leads,
        "valid_leads_count": valid_leads,
        "lead_valid_rate": lead_valid_rate,
        "lead_cost": lead_cost,
        "exposure_enter_rate": float(session.exposure_enter_rate or 0),
        "share_rate": float(session.share_rate or 0),
        "like_rate": float(session.like_rate or 0),
        "comment_rate": float(session.comment_rate or 0),
        "interaction_rate": float(session.interaction_rate or 0),
        "natural_traffic_ratio": float(session.natural_traffic_ratio or 0),
        "marketing_traffic_ratio": float(session.marketing_traffic_ratio or 0),
        "other_traffic_ratio": float(session.other_traffic_ratio or 0),
        "live_exposure_users": session.live_exposure_users or 0,
        "live_enter_users": session.live_enter_users or 0,
        "card_click_users": session.card_click_users or 0,
        "private_message_count": session.private_message_count or 0,
        "scene_leads_count": session.scene_leads_count or 0,
        "mini_windmill_click_count": session.mini_windmill_click_count or 0,
        "created_at": now,
        "updated_at": now,
    })


def sync_realtime_metrics(db, session_id: int):
    """
    同步分钟级实时指标（de_anchor_realtime_metrics）
    按 session_id + minute 聚合 live_metrics
    """
    # 先删除该 session 的旧数据
    db.query(DeAnchorRealtimeMetrics).filter(
        DeAnchorRealtimeMetrics.session_id == session_id
    ).delete()

    # 获取 session 信息
    session = db.query(LiveSession).get(session_id)
    room = db.query(LiveRoom).get(session.room_id) if session and session.room_id else None
    anchor_name = (session.anchor_name or (room.anchor_name if room else None)) if session else None
    session_title = session.session_title if session else None

    # 按分钟聚合 live_metrics
    rows = db.query(
        func.date_format(LiveMetric.metric_time, "%Y-%m-%d %H:%i:00").label("metric_minute"),
        func.avg(LiveMetric.online_count).label("avg_online"),
        func.max(LiveMetric.online_count).label("max_online"),
        func.avg(LiveMetric.exposure_count).label("avg_exposure"),
        func.avg(LiveMetric.enter_count).label("avg_enter"),
        func.sum(LiveMetric.like_count).label("total_like"),
        func.sum(LiveMetric.comment_count).label("total_comment"),
        func.sum(LiveMetric.follow_count).label("total_follow"),
        func.avg(LiveMetric.natural_traffic_count).label("avg_natural"),
        func.avg(LiveMetric.marketing_traffic_count).label("avg_marketing"),
        func.count(LiveMetric.id).label("cnt"),
    ).filter(
        LiveMetric.session_id == session_id
    ).group_by("metric_minute").order_by("metric_minute").all()

    now = datetime.utcnow()
    for r in rows:
        metric = DeAnchorRealtimeMetrics(
            session_id=session_id,
            anchor_name=anchor_name,
            session_title=session_title,
            metric_time=datetime.strptime(r.metric_minute, "%Y-%m-%d %H:%M:00") if r.metric_minute else now,
            avg_online_count=float(r.avg_online or 0),
            max_online_count=int(r.max_online or 0),
            avg_exposure_count=float(r.avg_exposure or 0),
            avg_enter_count=float(r.avg_enter or 0),
            total_like_count=int(r.total_like or 0),
            total_comment_count=int(r.total_comment or 0),
            total_follow_count=int(r.total_follow or 0),
            avg_natural_traffic=float(r.avg_natural or 0),
            avg_marketing_traffic=float(r.avg_marketing or 0),
            metric_count=int(r.cnt or 0),
        )
        db.add(metric)

    logger.info(f"  realtime_metrics: {len(rows)} 分钟聚合数据")


def sync_conversion_funnel(db, session_id: int):
    """
    同步转化漏斗（de_anchor_conversion_funnel）
    预计算 5 步转化率
    """
    # 先删除旧数据
    db.query(DeAnchorConversionFunnel).filter(
        DeAnchorConversionFunnel.session_id == session_id
    ).delete()

    session = db.query(LiveSession).get(session_id)
    if not session:
        return

    room = db.query(LiveRoom).get(session.room_id) if session.room_id else None
    anchor_name = session.anchor_name or (room.anchor_name if room else None)
    stat_date_val = session.live_start_time.date() if session.live_start_time else None

    # 漏斗步骤定义
    steps = [
        ("曝光", session.live_exposure_users or 0),
        ("进入", session.live_enter_users or 0),
        ("互动点击", session.card_click_users or 0),
        ("私信", session.private_message_count or 0),
        ("留资", session.leads_count or 0),
    ]

    prev_count = 0
    for i, (step_name, count) in enumerate(steps):
        rate = (count / prev_count) if prev_count > 0 and i > 0 else 0
        funnel = DeAnchorConversionFunnel(
            session_id=session_id,
            anchor_name=anchor_name,
            session_title=session.session_title,
            stat_date=stat_date_val,
            funnel_step=step_name,
            user_count=count,
            prev_step_user_count=prev_count,
            step_rate=rate,
        )
        db.add(funnel)
        prev_count = count
