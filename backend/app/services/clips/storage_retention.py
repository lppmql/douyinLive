"""直播回放容量治理；默认只告警，显式开启后才清理 replay.mp4。"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, settings
from app.core.logger import logger
from app.core.status import TaskStatus
from app.models.live_sessions import LiveSession
from app.models.scraper_tasks import ScraperTask


def _replay_files() -> list[tuple[int, Path]]:
    root = (Path(PROJECT_ROOT) / settings.CLIP_STORAGE_DIR).resolve()
    if not root.exists():
        return []
    files: list[tuple[int, Path]] = []
    for directory in root.iterdir():
        if not directory.is_dir() or not directory.name.isdigit():
            continue
        replay = directory / "replay.mp4"
        if replay.is_file() and replay.resolve().is_relative_to(root):
            files.append((int(directory.name), replay))
    return files


def _protected_session_ids(db: Session) -> set[int]:
    protected = {
        int(row[0])
        for row in db.query(LiveSession.id)
        .filter(LiveSession.live_status == "live")
        .all()
    }
    tasks = (
        db.query(ScraperTask)
        .filter(
            ScraperTask.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]),
            ScraperTask.task_type == "clip_task",
        )
        .all()
    )
    for task in tasks:
        value = task.session_id or (task.task_options_json or {}).get("session_id")
        if value:
            protected.add(int(value))
    return protected


def prune_replay_storage(db: Session) -> dict[str, Any]:
    """默认只统计告警；显式启用后按天数/容量清理且保护活动场次。"""
    protected = _protected_session_ids(db)
    now = datetime.now()
    cutoff = now - timedelta(days=settings.CLIP_REPLAY_RETENTION_DAYS)
    entries = []
    for session_id, path in _replay_files():
        stat = path.stat()
        entries.append(
            {
                "session_id": session_id,
                "path": path,
                "size": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime),
            }
        )

    current_bytes = sum(entry["size"] for entry in entries)
    max_bytes = int(settings.CLIP_REPLAY_MAX_GB * 1024**3)
    if not settings.CLIP_REPLAY_AUTO_DELETE:
        return {
            "cleanup_enabled": False,
            "capacity_exceeded": current_bytes > max_bytes,
            "replay_count": len(entries),
            "replay_bytes": current_bytes,
            "deleted_count": 0,
            "deleted_bytes": 0,
            "deleted": [],
            "protected_session_ids": sorted(protected),
        }

    deleted: list[dict[str, Any]] = []

    def remove(entry: dict[str, Any], reason: str) -> None:
        try:
            entry["path"].unlink(missing_ok=True)
            deleted.append(
                {
                    "session_id": entry["session_id"],
                    "bytes": entry["size"],
                    "reason": reason,
                }
            )
        except OSError as exc:
            logger.warning("回放清理失败 %s: %s", entry["path"], exc)

    for entry in sorted(entries, key=lambda item: item["modified_at"]):
        if entry["session_id"] not in protected and entry["modified_at"] < cutoff:
            remove(entry, "retention_days")

    remaining = [entry for entry in entries if entry["path"].exists()]
    current_bytes = sum(entry["size"] for entry in remaining)
    for entry in sorted(remaining, key=lambda item: item["modified_at"]):
        if current_bytes <= max_bytes:
            break
        if entry["session_id"] in protected:
            continue
        remove(entry, "capacity_limit")
        current_bytes -= entry["size"]

    final_entries = [entry for entry in entries if entry["path"].exists()]
    return {
        "cleanup_enabled": True,
        "capacity_exceeded": sum(entry["size"] for entry in final_entries) > max_bytes,
        "replay_count": len(final_entries),
        "replay_bytes": sum(entry["size"] for entry in final_entries),
        "deleted_count": len(deleted),
        "deleted_bytes": sum(entry["bytes"] for entry in deleted),
        "deleted": deleted,
        "protected_session_ids": sorted(protected),
    }


def replay_storage_stats() -> dict[str, int | bool]:
    """只读统计回放占用，供状态接口展示。"""
    entries = _replay_files()
    sizes = [path.stat().st_size for _session_id, path in entries]
    replay_bytes = sum(sizes)
    max_bytes = int(settings.CLIP_REPLAY_MAX_GB * 1024**3)
    return {
        "replay_count": len(entries),
        "replay_bytes": replay_bytes,
        "cleanup_enabled": settings.CLIP_REPLAY_AUTO_DELETE,
        "capacity_exceeded": replay_bytes > max_bytes,
    }
