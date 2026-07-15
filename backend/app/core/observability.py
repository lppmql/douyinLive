"""Trace、结构化日志与 Prometheus 指标。"""
from __future__ import annotations

import contextvars
import json
import logging
import time
import uuid
from datetime import datetime, timezone

from prometheus_client import Counter, Gauge, Histogram
from sqlalchemy import func, or_

from app.core.config import settings

trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")

HTTP_REQUESTS_TOTAL = Counter(
    "douyin_http_requests_total",
    "HTTP requests handled by the API",
    ("method", "route", "status"),
)
HTTP_REQUEST_DURATION = Histogram(
    "douyin_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ("method", "route"),
)
TASK_EVENTS_TOTAL = Counter(
    "douyin_task_events_total",
    "Task lifecycle events",
    ("task_type", "event", "status"),
)
KNOWLEDGE_SYNC_TOTAL = Counter(
    "douyin_knowledge_slice_sync_total",
    "Knowledge time slice sync results",
    ("result",),
)
KNOWLEDGE_SEARCH_TOTAL = Counter(
    "douyin_knowledge_search_total",
    "Knowledge searches",
    ("result",),
)
DATAEASE_SYNC_TOTAL = Counter(
    "douyin_dataease_sync_total",
    "DataEase session sync results",
    ("result",),
)
ASR_QUEUE_SIZE = Gauge("douyin_asr_queue_size", "Queued ASR tasks")
ASR_PROCESSING_COUNT = Gauge("douyin_asr_processing_count", "Processing ASR tasks")
ASR_CHUNK_STATUS = Gauge("douyin_asr_chunk_count", "ASR chunks by status", ("status",))
KNOWLEDGE_SLICE_COUNT = Gauge("douyin_knowledge_slice_count", "Knowledge time slices")
KNOWLEDGE_SESSION_COUNT = Gauge("douyin_knowledge_session_count", "Sessions covered by knowledge slices")
DATAEASE_SYNC_PENDING = Gauge("douyin_dataease_sync_pending", "Complete sessions pending DataEase sync")
COLLECTOR_LAST_SUCCESS = Gauge("douyin_collector_last_success_timestamp", "Last successful collector task unix timestamp")
MONITOR_RUNNING = Gauge("douyin_monitor_running", "Whether realtime monitor is running")


class JsonFormatter(logging.Formatter):
    """一行一个 JSON，便于 Loki、Filebeat 或容器日志采集。"""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", trace_id_var.get()),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TraceFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = trace_id_var.get()
        return True


def configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
    handler = logging.StreamHandler()
    handler.addFilter(TraceFilter())
    if settings.LOG_FORMAT.lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | trace=%(trace_id)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
    root.handlers.clear()
    root.addHandler(handler)


def new_trace_id(incoming: str | None = None) -> str:
    candidate = (incoming or "").strip()
    if candidate and len(candidate) <= 128 and all(char.isalnum() or char in "-_." for char in candidate):
        return candidate
    return uuid.uuid4().hex


def observe_http(method: str, route: str, status: int, started_at: float) -> None:
    HTTP_REQUESTS_TOTAL.labels(method=method, route=route, status=str(status)).inc()
    HTTP_REQUEST_DURATION.labels(method=method, route=route).observe(max(0, time.perf_counter() - started_at))


def refresh_runtime_metrics(db, monitor_running: bool) -> None:
    """抓取时刷新低基数运行指标，不影响业务写入。"""
    from app.models.asr_audio_chunks import AsrAudioChunk
    from app.models.asr_tasks import AsrTask
    from app.models.de_tables import DeLiveSessionAnchorSummary
    from app.models.knowledge_time_slices import KnowledgeTimeSlice
    from app.models.live_sessions import LiveSession
    from app.models.scraper_tasks import ScraperTask
    from app.services.sync.de_sync import source_data_outdated_condition

    ASR_QUEUE_SIZE.set(db.query(func.count(AsrTask.id)).filter(AsrTask.status == "queued").scalar() or 0)
    ASR_PROCESSING_COUNT.set(db.query(func.count(AsrTask.id)).filter(AsrTask.status == "processing").scalar() or 0)
    chunk_counts = dict(db.query(AsrAudioChunk.status, func.count(AsrAudioChunk.id)).group_by(AsrAudioChunk.status).all())
    for status in ("pending", "processing", "completed", "failed"):
        ASR_CHUNK_STATUS.labels(status=status).set(chunk_counts.get(status, 0))
    KNOWLEDGE_SLICE_COUNT.set(db.query(func.count(KnowledgeTimeSlice.id)).scalar() or 0)
    KNOWLEDGE_SESSION_COUNT.set(db.query(func.count(func.distinct(KnowledgeTimeSlice.session_id))).scalar() or 0)
    pending = db.query(func.count(LiveSession.id)).outerjoin(
        DeLiveSessionAnchorSummary,
        DeLiveSessionAnchorSummary.session_id == LiveSession.id,
    ).filter(
        LiveSession.detail_collection_status == "complete",
        or_(DeLiveSessionAnchorSummary.id.is_(None), source_data_outdated_condition()),
    ).scalar() or 0
    DATAEASE_SYNC_PENDING.set(pending)
    last_success = db.query(func.max(ScraperTask.completed_at)).filter(ScraperTask.status == "completed").scalar()
    COLLECTOR_LAST_SUCCESS.set(last_success.replace(tzinfo=timezone.utc).timestamp() if last_success else 0)
    MONITOR_RUNNING.set(1 if monitor_running else 0)
