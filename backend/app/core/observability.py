"""请求 Trace ID 与结构化日志。"""
from __future__ import annotations

import contextvars
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from app.core.config import settings

trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")


class JsonFormatter(logging.Formatter):
    """一行一个 JSON，便于日志文件、容器或外部日志平台采集。"""

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
    worker_log_path = os.getenv("ASR_WORKER_LOG_PATH", "").strip()
    if worker_log_path:
        # ASR 是长期运行的独立进程，固定轮转可防止一份日志再次占满本机磁盘。
        handler = RotatingFileHandler(
            worker_log_path,
            maxBytes=20 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
    else:
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

    # WebSocket 音频帧和逐条 SQL 会让长场次日志快速膨胀，只保留业务进度与异常。
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.DATABASE_ECHO else logging.WARNING
    )


def new_trace_id(incoming: str | None = None) -> str:
    candidate = (incoming or "").strip()
    if candidate and len(candidate) <= 128 and all(char.isalnum() or char in "-_." for char in candidate):
        return candidate
    return uuid.uuid4().hex
