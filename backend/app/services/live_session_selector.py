"""公共场次选择器使用的查询条件。

这里统一主播、日期和关键词的含义，避免话术、复盘、剪辑、知识库各写一套后
逐渐产生不同结果。日期以数据库中保存的北京时间开播时间为准，结束日期包含
当天，因此 SQL 使用“次日零点之前”的半开区间。
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import String, and_, case, cast, false, func, literal, or_, true
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


def build_session_anchor_key_condition(anchor_key: str) -> ColumnElement[bool]:
    """把透明主播键还原为字段条件，避免 MySQL 动态字符串排序规则冲突。"""
    prefix, separator, value = anchor_key.partition(":")
    if not separator or not value:
        return false()

    uid_is_blank = or_(LiveSession.douyin_uid.is_(None), LiveSession.douyin_uid == "")
    if prefix == "uid":
        return LiveSession.douyin_uid == value

    if prefix == "dyid":
        return and_(uid_is_blank, LiveSession.douyin_id == value)

    if prefix != "room":
        return false()

    room_id_text, name_separator, fallback_name = value.partition(":name:")
    try:
        room_id = int(room_id_text)
    except ValueError:
        return false()
    if not name_separator or room_id <= 0 or not fallback_name:
        return false()

    douyin_id_is_blank = or_(LiveSession.douyin_id.is_(None), LiveSession.douyin_id == "")
    anchor_name_is_blank = or_(LiveSession.anchor_name.is_(None), LiveSession.anchor_name == "")
    # fallback_name 生成时会 trim；这里仍直接比较原始字段，而不是重新拼接主播键。
    fallback_identity = or_(
        and_(
            LiveSession.anchor_name.is_not(None),
            LiveSession.anchor_name != "",
            func.trim(LiveSession.anchor_name) == fallback_name,
        ),
        and_(
            anchor_name_is_blank,
            LiveSession.anchor_nickname.is_not(None),
            LiveSession.anchor_nickname != "",
            func.trim(LiveSession.anchor_nickname) == fallback_name,
        ),
    )
    return and_(
        uid_is_blank,
        douyin_id_is_blank,
        LiveSession.room_id == room_id,
        fallback_identity,
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
        conditions.append(build_session_anchor_key_condition(normalized_anchor_key))

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
