"""主播排班与真实直播场次匹配、提醒计算。"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Iterable

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.anchor_schedules import AnchorSchedule
from app.models.live_sessions import LiveSession


MATCH_WINDOW_MINUTES = 120
MAX_SCHEDULE_RANGE_DAYS = 31
MIN_VALID_DURATION_MINUTES = 45


def _load_schedules(db: Session) -> list[AnchorSchedule]:
    return (
        db.query(AnchorSchedule)
        .filter(AnchorSchedule.active.is_(True))
        .order_by(AnchorSchedule.planned_start_time.asc(), AnchorSchedule.session_index.asc())
        .all()
    )


def _load_profile_sessions(db: Session, schedules: list[AnchorSchedule]) -> list[LiveSession]:
    all_keywords = sorted({keyword for item in schedules for keyword in (item.match_keywords or []) if keyword})
    if not all_keywords:
        return []
    return (
        db.query(LiveSession)
        .filter(or_(*(LiveSession.anchor_name.like(f"%{keyword}%") for keyword in all_keywords)))
        .order_by(LiveSession.live_start_time.desc(), LiveSession.id.desc())
        .limit(500)
        .all()
    )


def _combine(schedule_date: date, value: time) -> datetime:
    return datetime.combine(schedule_date, value)


def _planned_range(schedule_date: date, schedule: AnchorSchedule) -> tuple[datetime, datetime]:
    start = _combine(schedule_date, schedule.planned_start_time)
    end = _combine(schedule_date, schedule.planned_end_time)
    if end <= start:
        end += timedelta(days=1)
    return start, end


def _next_whole_hour(value: datetime) -> datetime:
    if value.minute == 0 and value.second == 0:
        return value + timedelta(hours=1)
    return value.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def _matches_anchor(session: LiveSession, keywords: Iterable[str]) -> bool:
    name = (session.anchor_name or "").lower()
    return any(keyword and keyword.lower() in name for keyword in keywords)


def _effective_duration_seconds(session: LiveSession, now: datetime) -> int:
    stored = max(int(session.live_duration_seconds or 0), 0)
    if session.live_status == "live" and session.live_start_time:
        return max(stored, max(int((now - session.live_start_time).total_seconds()), 0))
    if session.live_start_time and session.live_end_time:
        return max(stored, max(int((session.live_end_time - session.live_start_time).total_seconds()), 0))
    return stored


def _serialize_actual(session: LiveSession, now: datetime) -> dict:
    return {
        "id": session.id,
        "anchor_name": session.anchor_name,
        "anchor_avatar_url": session.anchor_avatar_url,
        "live_start_time": session.live_start_time.isoformat() if session.live_start_time else None,
        "live_end_time": session.live_end_time.isoformat() if session.live_end_time else None,
        "live_duration_seconds": _effective_duration_seconds(session, now),
        "live_status": session.live_status,
    }


def _append_invalid_stat(stat: dict, schedule_date: date, actual_payload: dict, is_extra: bool) -> None:
    """按日期归集无效场次，保留真实场次和时长供前端穿透展示。"""
    invalid_date = schedule_date.isoformat()
    invalid_item = next(
        (item for item in stat["invalid_by_date"] if item["schedule_date"] == invalid_date),
        None,
    )
    if invalid_item is None:
        invalid_item = {
            "schedule_date": invalid_date,
            "count": 0,
            "session_ids": [],
            "live_start_times": [],
            "durations_seconds": [],
            "extra_flags": [],
        }
        stat["invalid_by_date"].append(invalid_item)
    stat["invalid_count"] += 1
    invalid_item["count"] += 1
    invalid_item["session_ids"].append(actual_payload["id"])
    invalid_item["live_start_times"].append(actual_payload["live_start_time"])
    invalid_item["durations_seconds"].append(actual_payload["live_duration_seconds"])
    invalid_item["extra_flags"].append(is_extra)


def _match_sessions(
    schedules: list[AnchorSchedule],
    sessions: list[LiveSession],
    schedule_date: date,
) -> dict[int, LiveSession]:
    """按主播和计划时间做一对一最近匹配，防止同一真实场次重复占用。"""
    matched: dict[int, LiveSession] = {}
    used_ids: set[int] = set()
    grouped: dict[str, list[AnchorSchedule]] = defaultdict(list)
    for schedule in schedules:
        grouped[schedule.source_anchor_name].append(schedule)

    for anchor_schedules in grouped.values():
        keywords = list(anchor_schedules[0].match_keywords or [])
        candidates = [item for item in sessions if _matches_anchor(item, keywords)]
        for schedule in sorted(anchor_schedules, key=lambda item: item.planned_start_time):
            planned_start, _ = _planned_range(schedule_date, schedule)
            available = [
                item
                for item in candidates
                if item.id not in used_ids
                and item.live_start_time
                and abs((item.live_start_time - planned_start).total_seconds()) <= MATCH_WINDOW_MINUTES * 60
            ]
            if not available:
                continue
            actual = min(available, key=lambda item: abs((item.live_start_time - planned_start).total_seconds()))
            matched[schedule.id] = actual
            used_ids.add(actual.id)
    return matched


def build_schedule_dashboard(
    db: Session,
    schedule_date: date,
    now: datetime | None = None,
    schedules: list[AnchorSchedule] | None = None,
    profile_sessions: list[LiveSession] | None = None,
) -> dict:
    """返回指定日期的计划、真实执行情况和已到期提醒。"""
    now = now or datetime.now()
    schedules = schedules if schedules is not None else _load_schedules(db)
    day_start = datetime.combine(schedule_date, time.min)
    day_end = day_start + timedelta(days=1)
    all_keywords = sorted({keyword for item in schedules for keyword in (item.match_keywords or []) if keyword})
    session_query = db.query(LiveSession).filter(
        LiveSession.live_start_time >= day_start,
        LiveSession.live_start_time < day_end,
    )
    if all_keywords:
        session_query = session_query.filter(
            or_(*(LiveSession.anchor_name.like(f"%{keyword}%") for keyword in all_keywords))
        )
    sessions = session_query.order_by(LiveSession.live_start_time.asc(), LiveSession.id.asc()).all()
    profile_sessions = profile_sessions if profile_sessions is not None else _load_profile_sessions(db, schedules)
    matched = _match_sessions(schedules, sessions, schedule_date)

    rows: list[dict] = []
    reminders: list[dict] = []
    anchor_stats: dict[str, dict] = {}
    compliant_duration_count = 0

    for schedule in schedules:
        planned_start, planned_end = _planned_range(schedule_date, schedule)
        planned_hour_start = planned_start.replace(minute=0, second=0, microsecond=0)
        due_at = _next_whole_hour(planned_start)
        actual = matched.get(schedule.id)
        warnings: list[str] = []
        status = "upcoming"
        actual_payload = None

        if actual:
            actual_payload = _serialize_actual(actual, now)
            duration_seconds = actual_payload["live_duration_seconds"]
            is_live = actual.live_status == "live"
            invalid_duration = not is_live and duration_seconds < MIN_VALID_DURATION_MINUTES * 60
            duration_short = (
                not is_live
                and not invalid_duration
                and duration_seconds < schedule.expected_duration_minutes * 60
            )
            crossed_hour = bool(
                actual.live_start_time
                and (actual.live_start_time < planned_hour_start or actual.live_start_time >= due_at)
            )
            if is_live:
                status = "live"
            elif invalid_duration:
                status = "invalid"
                warnings.append(
                    f"实际直播不足 {MIN_VALID_DURATION_MINUTES} 分钟，标记为无效场次"
                    f"（实际 {duration_seconds // 60} 分 {duration_seconds % 60} 秒）"
                )
            elif duration_short:
                status = "duration_short"
                short_minutes = max(schedule.expected_duration_minutes - round(duration_seconds / 60), 0)
                warnings.append(f"实际直播不足 {schedule.expected_duration_minutes} 分钟，少 {short_minutes} 分钟")
            else:
                status = "completed"
                compliant_duration_count += 1
            if crossed_hour:
                warnings.append(
                    "实际开播不在计划所在整点时段"
                    f"（{planned_hour_start.strftime('%H:%M')}-{(due_at - timedelta(minutes=1)).strftime('%H:%M')}）"
                )
        elif now >= due_at:
            status = "missing"
            warnings.append("计划场次已到期，尚未匹配到真实开播记录")

        for warning in warnings:
            if status == "missing":
                reminder_type = "missing"
            elif "无效场次" in warning:
                reminder_type = "invalid"
            elif "不足" in warning:
                reminder_type = "duration"
            else:
                reminder_type = "cross_hour"
            reminders.append(
                {
                    "type": reminder_type,
                    "severity": "error" if reminder_type in {"missing", "invalid"} else "warning",
                    "anchor_name": schedule.display_name,
                    "session_index": schedule.session_index,
                    "message": warning,
                    "schedule_date": schedule_date.isoformat(),
                    "planned_start_time": planned_start.isoformat(),
                    "session_id": actual.id if actual else None,
                    "is_extra": False,
                }
            )

        stat = anchor_stats.setdefault(
            schedule.source_anchor_name,
            {
                "source_anchor_name": schedule.source_anchor_name,
                "display_name": schedule.display_name,
                "room_name": schedule.room_name,
                "network_name": schedule.network_name,
                "expected_count": 0,
                "matched_count": 0,
                "completed_count": 0,
                "warning_count": 0,
                "missing_count": 0,
                "missing_by_date": [],
                "invalid_count": 0,
                "invalid_by_date": [],
                "extra_count": 0,
                "extra_by_date": [],
                "anchor_avatar_url": None,
                "anchor_avatar_session_id": None,
                "actual_anchor_name": None,
            },
        )
        if not stat["anchor_avatar_url"]:
            profile = next(
                (item for item in profile_sessions if _matches_anchor(item, schedule.match_keywords or [])),
                None,
            )
            if profile:
                stat["anchor_avatar_url"] = profile.anchor_avatar_url
                stat["anchor_avatar_session_id"] = profile.id
                stat["actual_anchor_name"] = profile.anchor_name
        stat["expected_count"] += 1
        stat["matched_count"] += int(actual is not None)
        stat["completed_count"] += int(status == "completed")
        stat["warning_count"] += len(warnings)
        if status == "missing":
            stat["missing_count"] += 1
            missing_date = schedule_date.isoformat()
            missing_item = next(
                (item for item in stat["missing_by_date"] if item["schedule_date"] == missing_date),
                None,
            )
            if missing_item is None:
                missing_item = {"schedule_date": missing_date, "count": 0, "session_indexes": []}
                stat["missing_by_date"].append(missing_item)
            missing_item["count"] += 1
            missing_item["session_indexes"].append(schedule.session_index)
        if status == "invalid" and actual_payload:
            _append_invalid_stat(stat, schedule_date, actual_payload, False)
        if actual:
            stat["anchor_avatar_url"] = actual.anchor_avatar_url or stat["anchor_avatar_url"]
            stat["anchor_avatar_session_id"] = actual.id if actual.anchor_avatar_url else stat["anchor_avatar_session_id"]
            stat["actual_anchor_name"] = actual.anchor_name or stat["actual_anchor_name"]

        rows.append(
            {
                "id": schedule.id,
                "schedule_date": schedule_date.isoformat(),
                "source_anchor_name": schedule.source_anchor_name,
                "display_name": schedule.display_name,
                "room_name": schedule.room_name,
                "network_name": schedule.network_name,
                "session_index": schedule.session_index,
                "extra_index": None,
                "is_extra": False,
                "planned_start_time": planned_start.isoformat(),
                "planned_end_time": planned_end.isoformat(),
                "expected_duration_minutes": schedule.expected_duration_minutes,
                "status": status,
                "warnings": warnings,
                "actual_session": actual_payload,
            }
        )

    matched_session_ids = {session.id for session in matched.values()}
    assigned_extra_ids: set[int] = set()
    schedules_by_anchor: dict[str, list[AnchorSchedule]] = defaultdict(list)
    for schedule in schedules:
        schedules_by_anchor[schedule.source_anchor_name].append(schedule)

    for source_anchor_name, anchor_schedules in schedules_by_anchor.items():
        representative = anchor_schedules[0]
        candidates = [item for item in sessions if _matches_anchor(item, representative.match_keywords or [])]
        overflow_count = max(len(candidates) - len(anchor_schedules), 0)
        if overflow_count == 0:
            continue
        planned_starts = [_planned_range(schedule_date, item)[0] for item in anchor_schedules]
        unmatched_candidates = [
            item
            for item in candidates
            if item.id not in matched_session_ids and item.id not in assigned_extra_ids and item.live_start_time
        ]
        extra_sessions = sorted(
            sorted(
                unmatched_candidates,
                key=lambda item: min(
                    abs((item.live_start_time - planned_start).total_seconds()) for planned_start in planned_starts
                ),
                reverse=True,
            )[:overflow_count],
            key=lambda item: (item.live_start_time, item.id),
        )
        stat = anchor_stats[source_anchor_name]
        for extra_index, actual in enumerate(extra_sessions, start=1):
            assigned_extra_ids.add(actual.id)
            actual_payload = _serialize_actual(actual, now)
            is_live = actual.live_status == "live"
            invalid_duration = (
                not is_live and actual_payload["live_duration_seconds"] < MIN_VALID_DURATION_MINUTES * 60
            )
            extra_warnings: list[str] = []
            if invalid_duration:
                duration_seconds = actual_payload["live_duration_seconds"]
                extra_warnings.append(
                    f"实际直播不足 {MIN_VALID_DURATION_MINUTES} 分钟，标记为无效加场"
                    f"（实际 {duration_seconds // 60} 分 {duration_seconds % 60} 秒）"
                )
                _append_invalid_stat(stat, schedule_date, actual_payload, True)
                stat["warning_count"] += 1
                reminders.append(
                    {
                        "type": "invalid",
                        "severity": "error",
                        "anchor_name": representative.display_name,
                        "session_index": extra_index,
                        "message": extra_warnings[0],
                        "schedule_date": schedule_date.isoformat(),
                        "planned_start_time": actual_payload["live_start_time"],
                        "session_id": actual.id,
                        "is_extra": True,
                    }
                )
            stat["extra_count"] += 1
            extra_date = schedule_date.isoformat()
            extra_item = next(
                (item for item in stat["extra_by_date"] if item["schedule_date"] == extra_date),
                None,
            )
            if extra_item is None:
                extra_item = {
                    "schedule_date": extra_date,
                    "count": 0,
                    "session_ids": [],
                    "live_start_times": [],
                }
                stat["extra_by_date"].append(extra_item)
            extra_item["count"] += 1
            extra_item["session_ids"].append(actual.id)
            extra_item["live_start_times"].append(actual_payload["live_start_time"])
            stat["anchor_avatar_url"] = actual.anchor_avatar_url or stat["anchor_avatar_url"]
            stat["anchor_avatar_session_id"] = actual.id if actual.anchor_avatar_url else stat["anchor_avatar_session_id"]
            stat["actual_anchor_name"] = actual.anchor_name or stat["actual_anchor_name"]
            rows.append(
                {
                    "id": actual.id,
                    "schedule_date": extra_date,
                    "source_anchor_name": source_anchor_name,
                    "display_name": representative.display_name,
                    "room_name": representative.room_name,
                    "network_name": representative.network_name,
                    "session_index": extra_index,
                    "extra_index": extra_index,
                    "is_extra": True,
                    "planned_start_time": None,
                    "planned_end_time": None,
                    "expected_duration_minutes": representative.expected_duration_minutes,
                    "status": "invalid" if invalid_duration else "extra",
                    "warnings": extra_warnings,
                    "actual_session": actual_payload,
                }
            )

    rows.sort(
        key=lambda row: row["planned_start_time"]
        or (row["actual_session"] or {}).get("live_start_time")
        or f"{schedule_date.isoformat()}T23:59:59"
    )
    matched_count = len(matched)
    return {
        "schedule_date": schedule_date.isoformat(),
        "start_date": schedule_date.isoformat(),
        "end_date": schedule_date.isoformat(),
        "day_count": 1,
        "generated_at": now.isoformat(),
        "source_name": schedules[0].source_name if schedules else "排班.xls",
        "rule": {
            "expected_duration_minutes": 80,
            "minimum_valid_duration_minutes": MIN_VALID_DURATION_MINUTES,
            "four_session_anchors": ["刘文豪", "王路权（大全）"],
            "default_session_count": 3,
            "cross_hour_definition": "实际开播须在计划时间所在自然小时内，提前或延后跨出该小时均提醒",
        },
        "summary": {
            "planned_count": len(schedules),
            "matched_count": matched_count,
            "completed_count": sum(1 for row in rows if row["status"] == "completed"),
            "live_count": sum(
                1 for row in rows if row["actual_session"] and row["actual_session"]["live_status"] == "live"
            ),
            "upcoming_count": sum(1 for row in rows if row["status"] == "upcoming"),
            "missing_count": sum(1 for row in rows if row["status"] == "missing"),
            "duration_short_count": sum(1 for row in rows if row["status"] == "duration_short"),
            "invalid_count": sum(1 for row in rows if row["status"] == "invalid"),
            "extra_count": sum(1 for row in rows if row["is_extra"]),
            "cross_hour_count": sum(1 for item in reminders if item["type"] == "cross_hour"),
            "duration_compliant_count": compliant_duration_count,
            "reminder_count": len(reminders),
        },
        "anchors": list(anchor_stats.values()),
        "rows": rows,
        "reminders": reminders,
    }


def build_schedule_range_dashboard(
    db: Session,
    start_date: date,
    end_date: date,
    now: datetime | None = None,
) -> dict:
    """汇总起止日期内的每日排班，日期范围包含首尾两天。"""
    if end_date < start_date:
        raise ValueError("结束日期不能早于开始日期")
    day_count = (end_date - start_date).days + 1
    if day_count > MAX_SCHEDULE_RANGE_DAYS:
        raise ValueError(f"日期范围最多支持 {MAX_SCHEDULE_RANGE_DAYS} 天")

    now = now or datetime.now()
    schedules = _load_schedules(db)
    profile_sessions = _load_profile_sessions(db, schedules)
    dashboards = [
        build_schedule_dashboard(
            db,
            start_date + timedelta(days=offset),
            now,
            schedules=schedules,
            profile_sessions=profile_sessions,
        )
        for offset in range(day_count)
    ]
    if not dashboards:
        return {}

    summary_keys = dashboards[0]["summary"].keys()
    summary = {key: sum(item["summary"][key] for item in dashboards) for key in summary_keys}
    anchor_stats: dict[str, dict] = {}
    for dashboard in dashboards:
        for anchor in dashboard["anchors"]:
            stat = anchor_stats.setdefault(
                anchor["source_anchor_name"],
                {
                    **anchor,
                    "expected_count": 0,
                    "matched_count": 0,
                    "completed_count": 0,
                    "warning_count": 0,
                    "missing_count": 0,
                    "missing_by_date": [],
                    "invalid_count": 0,
                    "invalid_by_date": [],
                    "extra_count": 0,
                    "extra_by_date": [],
                },
            )
            for key in (
                "expected_count",
                "matched_count",
                "completed_count",
                "warning_count",
                "missing_count",
                "invalid_count",
                "extra_count",
            ):
                stat[key] += anchor[key]
            for missing_item in anchor["missing_by_date"]:
                existing_item = next(
                    (
                        item
                        for item in stat["missing_by_date"]
                        if item["schedule_date"] == missing_item["schedule_date"]
                    ),
                    None,
                )
                if existing_item is None:
                    stat["missing_by_date"].append(
                        {**missing_item, "session_indexes": list(missing_item["session_indexes"])}
                    )
                else:
                    existing_item["count"] += missing_item["count"]
                    existing_item["session_indexes"].extend(missing_item["session_indexes"])
            for invalid_item in anchor["invalid_by_date"]:
                existing_invalid_item = next(
                    (
                        item
                        for item in stat["invalid_by_date"]
                        if item["schedule_date"] == invalid_item["schedule_date"]
                    ),
                    None,
                )
                if existing_invalid_item is None:
                    stat["invalid_by_date"].append(
                        {
                            **invalid_item,
                            "session_ids": list(invalid_item["session_ids"]),
                            "live_start_times": list(invalid_item["live_start_times"]),
                            "durations_seconds": list(invalid_item["durations_seconds"]),
                            "extra_flags": list(invalid_item["extra_flags"]),
                        }
                    )
                else:
                    existing_invalid_item["count"] += invalid_item["count"]
                    existing_invalid_item["session_ids"].extend(invalid_item["session_ids"])
                    existing_invalid_item["live_start_times"].extend(invalid_item["live_start_times"])
                    existing_invalid_item["durations_seconds"].extend(invalid_item["durations_seconds"])
                    existing_invalid_item["extra_flags"].extend(invalid_item["extra_flags"])
            for extra_item in anchor["extra_by_date"]:
                existing_extra_item = next(
                    (
                        item
                        for item in stat["extra_by_date"]
                        if item["schedule_date"] == extra_item["schedule_date"]
                    ),
                    None,
                )
                if existing_extra_item is None:
                    stat["extra_by_date"].append(
                        {
                            **extra_item,
                            "session_ids": list(extra_item["session_ids"]),
                            "live_start_times": list(extra_item["live_start_times"]),
                        }
                    )
                else:
                    existing_extra_item["count"] += extra_item["count"]
                    existing_extra_item["session_ids"].extend(extra_item["session_ids"])
                    existing_extra_item["live_start_times"].extend(extra_item["live_start_times"])
            if anchor["anchor_avatar_url"]:
                stat["anchor_avatar_url"] = anchor["anchor_avatar_url"]
                stat["anchor_avatar_session_id"] = anchor["anchor_avatar_session_id"]
                stat["actual_anchor_name"] = anchor["actual_anchor_name"]

    for stat in anchor_stats.values():
        stat["missing_by_date"].sort(key=lambda item: item["schedule_date"])
        stat["invalid_by_date"].sort(key=lambda item: item["schedule_date"])
        stat["extra_by_date"].sort(key=lambda item: item["schedule_date"])

    return {
        "schedule_date": start_date.isoformat(),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "day_count": day_count,
        "generated_at": now.isoformat(),
        "source_name": dashboards[0]["source_name"],
        "rule": dashboards[0]["rule"],
        "summary": summary,
        "anchors": list(anchor_stats.values()),
        "rows": [row for dashboard in dashboards for row in dashboard["rows"]],
        "reminders": [reminder for dashboard in dashboards for reminder in dashboard["reminders"]],
    }
