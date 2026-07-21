"""话术转写模块 — Pydantic 响应模型"""

from __future__ import annotations
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field
from app.core.status import TaskStatus


# ── 排队 ──

class TranscriptQueueResponse(BaseModel):
    """POST /transcripts/{session_id}/queue"""
    task_id: int
    status: str
    created: bool


class TranscriptBatchResult(BaseModel):
    anchor_name: str = ""
    session_id: int
    duration_seconds: int | None = None
    task_id: int
    status: str
    created: bool


class TranscriptBatchResponse(BaseModel):
    """POST /transcripts/batch/queue-by-anchor"""
    anchor_count: int = 0
    selected_count: int = 0
    created_count: int = 0
    tasks: list[TranscriptBatchResult] = Field(default_factory=list)


# ── 任务状态 ──

class TranscriptTaskStatusResponse(BaseModel):
    """GET /transcripts/tasks/status"""
    queued: int = 0
    processing: int = 0
    completed: int = 0
    failed: int = 0


class TranscriptTaskOut(BaseModel):
    """GET /transcripts/tasks 单条任务"""
    id: int
    session_id: int | None = None
    status: str = TaskStatus.FAILED
    task_type: str = "offline"
    anchor_name: str = "未知主播"
    session_title: str = "未命名直播场次"
    live_start_time: datetime | None = None
    live_duration_seconds: int = 0
    segment_count: int = 0
    error_message: str | None = None
    postprocess_status: str = TaskStatus.PENDING
    postprocess_error: str | None = None
    postprocess_result: Any | None = None
    postprocess_attempt_count: int = 0
    postprocess_started_at: datetime | None = None
    postprocess_completed_at: datetime | None = None
    retry_count: int = 0
    max_retries: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ── 分段 / 全文 ──

class TranscriptSegmentOut(BaseModel):
    """GET /transcripts/{session_id}/segments"""
    id: int
    session_id: int | None = None
    segment_start: float = 0
    segment_end: float = 0
    text_content: str = ""
    segment_type: str = ""
    asr_status: str = TaskStatus.PENDING
    ai_score: float | None = None


class TranscriptFullTextResponse(BaseModel):
    """GET /transcripts/{session_id}/full-text"""
    id: int | None = None
    full_text: str = ""
    available: bool = False
