"""采集日志上下文与安全展示适配。

数据库仍保存真实结构化数据；接口返回前在这里补齐主播、场次和任务信息，
同时过滤 Cookie、Token、流地址等不应该出现在运维页面中的敏感内容。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.models.scraper_logs import ScraperLog
from app.models.scraper_tasks import ScraperTask


SENSITIVE_KEY_PARTS = (
    "authorization",
    "browser_fingerprint",
    "cookie",
    "fingerprint",
    "header",
    "m3u8",
    "password",
    "qr_",
    "storage_state",
    "stream_url",
    "token",
    "user_agent",
)

CONTEXT_KEYS = {
    "anchor_name",
    "anchor_nickname",
    "event",
    "event_type",
    "live_start_time",
    "room_id",
    "room_id_str",
    "session_id",
    "session_title",
    "stage",
    "task_type",
}


def _safe_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    text = str(value)
    return f"{text[:1999]}…" if len(text) > 2000 else text


def sanitize_log_data(value: Any, *, depth: int = 0) -> Any:
    """递归过滤敏感字段并限制异常大对象，避免日志详情再次拖慢页面。"""
    if depth >= 4:
        return _safe_scalar(value)
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            normalized = key.lower()
            if any(part in normalized for part in SENSITIVE_KEY_PARTS):
                continue
            result[key] = sanitize_log_data(item, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        visible = [sanitize_log_data(item, depth=depth + 1) for item in items[:20]]
        if len(items) > 20:
            visible.append({"omitted_count": len(items) - 20})
        return visible
    return _safe_scalar(value)


def _payload(log: ScraperLog) -> dict[str, Any]:
    return log.raw_json if isinstance(log.raw_json, dict) else {}


def _merged_details(payload: dict[str, Any]) -> dict[str, Any]:
    details = payload.get("details")
    merged = {key: value for key, value in payload.items() if key != "details"}
    if isinstance(details, dict):
        merged.update(details)
    return merged


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def serialize_collector_logs(db: Session, rows: Iterable[ScraperLog]) -> list[dict[str, Any]]:
    """批量补齐日志上下文，避免逐行查询造成页面卡顿。"""
    logs = list(rows)
    task_ids = {row.task_id for row in logs if row.task_id}
    tasks = {
        task.id: task
        for task in db.query(ScraperTask).filter(ScraperTask.id.in_(task_ids)).all()
    } if task_ids else {}

    prepared: list[tuple[ScraperLog, dict[str, Any], dict[str, Any], int | None]] = []
    session_ids: set[int] = set()
    for log in logs:
        payload = _payload(log)
        details = _merged_details(payload)
        task = tasks.get(log.task_id)
        session_id = (
            log.session_id
            or _as_int(details.get("session_id"))
            or (task.session_id if task else None)
        )
        if session_id:
            session_ids.add(session_id)
        prepared.append((log, payload, details, session_id))

    sessions = {
        session.id: session
        for session in db.query(LiveSession).filter(LiveSession.id.in_(session_ids)).all()
    } if session_ids else {}
    room_ids = {session.room_id for session in sessions.values() if session.room_id}
    rooms = {
        room.id: room
        for room in db.query(LiveRoom).filter(LiveRoom.id.in_(room_ids)).all()
    } if room_ids else {}

    result = []
    for log, payload, details, session_id in prepared:
        task = tasks.get(log.task_id)
        session = sessions.get(session_id)
        room = rooms.get(session.room_id) if session and session.room_id else None
        anchor_name = (
            log.anchor_name
            or details.get("anchor_name")
            or details.get("anchor_nickname")
            or (session.anchor_name if session else None)
            or (session.anchor_nickname if session else None)
            or (room.anchor_name if room else None)
        )
        session_title = log.session_title or details.get("session_title") or (session.session_title if session else None)
        room_id_str = (
            log.room_id_str
            or details.get("room_id_str")
            or details.get("room_id")
            or (room.room_id_str if room else None)
        )
        stage = log.stage or payload.get("stage") or details.get("stage")
        event_type = log.event_type or payload.get("event") or payload.get("event_type")
        task_type = details.get("task_type") or (task.task_type if task else None)

        data_details = {
            key: value
            for key, value in details.items()
            if key not in CONTEXT_KEYS
        }
        result.append({
            "id": log.id,
            "task_id": log.task_id,
            "level": "warn" if log.level == "warning" else log.level,
            "message": log.message,
            "raw_json": sanitize_log_data(payload),
            "session_id": session_id,
            "anchor_name": str(anchor_name)[:100] if anchor_name else None,
            "session_title": str(session_title)[:255] if session_title else None,
            "live_start_time": session.live_start_time if session else None,
            "room_id_str": str(room_id_str)[:100] if room_id_str else None,
            "task_type": str(task_type)[:50] if task_type else None,
            "event_type": str(event_type)[:50] if event_type else None,
            "stage": str(stage)[:50] if stage else None,
            "data_details": sanitize_log_data(data_details),
            "created_at": log.created_at,
        })
    return result


def add_collector_log(
    db: Session,
    *,
    level: str,
    message: str,
    task_id: int | None = None,
    session: LiveSession | None = None,
    room_id_str: str | None = None,
    stage: str | None = None,
    event_type: str | None = None,
    details: dict[str, Any] | None = None,
) -> ScraperLog:
    """新增一条带完整业务上下文的日志，由调用方决定何时提交事务。"""
    payload = {
        "stage": stage,
        "event": event_type,
        "session_id": session.id if session else None,
        "anchor_name": (session.anchor_name or session.anchor_nickname) if session else None,
        "session_title": session.session_title if session else None,
        "room_id": room_id_str,
        "details": sanitize_log_data(details or {}),
    }
    log = ScraperLog(
        task_id=task_id,
        level=level,
        message=message,
        raw_json={key: value for key, value in payload.items() if value not in (None, {})},
        session_id=session.id if session else None,
        anchor_name=(session.anchor_name or session.anchor_nickname) if session else None,
        session_title=session.session_title if session else None,
        room_id_str=room_id_str,
        event_type=event_type,
        stage=stage,
    )
    db.add(log)
    return log
