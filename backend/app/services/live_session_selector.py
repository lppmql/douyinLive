"""公共场次选择器使用的查询条件。

这里统一主播、日期和关键词的含义，避免话术、复盘、剪辑、知识库各写一套后
逐渐产生不同结果。日期以数据库中保存的北京时间开播时间为准，结束日期包含
当天，因此 SQL 使用“次日零点之前”的半开区间。
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import String, and_, case, cast, func, literal, or_, true
from sqlalchemy.sql.elements import ColumnElement

from app.models.live_sessions import LiveSession


def build_session_anchor_key_expression():
    """生成主播键：稳定 ID 优先，最终才用直播间与规范化身份快照。"""
    fallback_name = func.trim(
        func.coalesce(
            func.nullif(LiveSession.anchor_name, ""),
            func.nullif(LiveSession.anchor_nickname, ""),
            literal(""),
        )
    )
    return case(
        (
            and_(LiveSession.douyin_uid.is_not(None), LiveSession.douyin_uid != ""),
            literal("uid:") + LiveSession.douyin_uid,
        ),
        else_=case(
            (
                and_(LiveSession.douyin_id.is_not(None), LiveSession.douyin_id != ""),
                literal("dyid:") + LiveSession.douyin_id,
            ),
            else_=(
                literal("room:")
                + cast(LiveSession.room_id, String)
                + literal(":name:")
                + fallback_name
            ),
        ),
    )


def build_session_selector_condition(
    *,
    search: str | None = None,
    anchor_key: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> ColumnElement[bool]:
    """构造公共场次筛选条件；未传条件时返回恒真表达式。"""
    if start_date and end_date and start_date > end_date:
        raise ValueError("开始日期不能晚于结束日期")

    conditions: list[ColumnElement[bool]] = []
    normalized_anchor_key = (anchor_key or "").strip()
    if normalized_anchor_key:
        # 直接和服务端生成的透明键比较，避免解析昵称中的冒号等合法字符。
        conditions.append(build_session_anchor_key_expression() == normalized_anchor_key)

    if start_date:
        conditions.append(LiveSession.live_start_time >= datetime.combine(start_date, time.min))
    if end_date:
        conditions.append(
            LiveSession.live_start_time < datetime.combine(end_date + timedelta(days=1), time.min)
        )

    normalized_search = (search or "").strip()
    if normalized_search:
        pattern = f"%{normalized_search}%"
        conditions.append(
            or_(
                cast(LiveSession.id, String).like(pattern),
                LiveSession.session_title.like(pattern),
                LiveSession.anchor_name.like(pattern),
                LiveSession.anchor_nickname.like(pattern),
                LiveSession.douyin_id.like(pattern),
            )
        )

    return and_(*conditions) if conditions else true()
