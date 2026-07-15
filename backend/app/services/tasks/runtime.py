"""统一任务标识、心跳和 Redis Streams 生命周期事件。"""
import json
import os
import socket
from datetime import datetime
from typing import Any
from uuid import uuid4

from redis import Redis

from app.core.config import settings
from app.core.observability import TASK_EVENTS_TOTAL
from app.core.logger import logger


def current_worker_id(prefix: str) -> str:
    """生成可定位到进程的 Worker 标识。"""
    return f"{prefix}:{socket.gethostname()}:{os.getpid()}"[:100]


def ensure_task_identity(task: Any, task_kind: str, idempotency_key: str | None = None) -> None:
    """为新旧任务补齐稳定标识，不覆盖已有值。"""
    task.trace_id = task.trace_id or uuid4().hex
    task.idempotency_key = task.idempotency_key or idempotency_key or f"{task_kind}:{uuid4().hex}"


def touch_task(task: Any, worker_id: str | None = None) -> None:
    """更新数据库任务心跳。调用方负责提交事务。"""
    task.heartbeat_at = datetime.utcnow()
    if worker_id:
        task.worker_id = worker_id[:100]


def publish_task_event(
    task_kind: str,
    task: Any,
    event: str,
    details: dict[str, Any] | None = None,
) -> str | None:
    """将任务事件写入可回放的 Redis Stream；Redis 异常不阻断业务。"""
    payload = {
        "event": event,
        "task_kind": task_kind,
        "task_id": str(getattr(task, "id", "") or ""),
        "status": str(getattr(task, "status", "")),
        "trace_id": str(getattr(task, "trace_id", "") or ""),
        "worker_id": str(getattr(task, "worker_id", "") or ""),
        "retry_count": str(getattr(task, "retry_count", 0) or 0),
        "occurred_at": datetime.utcnow().isoformat(timespec="milliseconds"),
        "details": json.dumps(details or {}, ensure_ascii=False, default=str),
    }
    client = None
    TASK_EVENTS_TOTAL.labels(
        task_type=task_kind,
        event=event,
        status=str(getattr(task, "status", "unknown") or "unknown"),
    ).inc()
    try:
        client = Redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=1,
            socket_timeout=1,
            decode_responses=True,
        )
        return client.xadd(
            settings.TASK_EVENT_STREAM,
            payload,
            maxlen=max(100, settings.TASK_EVENT_STREAM_MAXLEN),
            approximate=True,
        )
    except Exception as exc:
        logger.warning("任务事件写入 Redis Stream 失败，不阻断业务: %s", exc)
        return None
    finally:
        if client:
            client.close()
