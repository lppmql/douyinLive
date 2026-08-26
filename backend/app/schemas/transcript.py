"""话术转写模块 — Pydantic 响应模型"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field
from app.core.status import TaskStatus


# ── 排队 ──


class TranscriptQueueResponse(BaseModel):
    """POST /transcripts/{session_id}/queue"""

    task_id: int
    status: str
    created: bool
    queue_source: Literal["auto", "manual"] = "manual"
    exclusive_active: bool = True


class TranscriptDispatchPolicyUpdate(BaseModel):
    """PUT /transcripts/dispatch-policy"""

    order_mode: Literal["smart", "latest", "fifo"]


class TranscriptDispatchPolicyOut(BaseModel):
    """GET /transcripts/dispatch-policy"""

    order_mode: Literal["smart", "latest", "fifo"] = "smart"
    manual_active: bool = False
    manual_task_id: int | None = None
    manual_session_id: int | None = None
    auto_scope_timezone: str = "Asia/Shanghai"
    auto_scope_description: str


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
    cancelled: int = 0
    needs_attention: int = 0


class TranscriptTaskOut(BaseModel):
    """GET /transcripts/tasks 单条任务"""

    id: int
    session_id: int | None = None
    status: str = TaskStatus.FAILED
    task_type: str = "offline"
    queue_source: Literal["auto", "manual"] = "auto"
    priority: int = 50
    queue_position: int | None = None
    cancel_requested: bool = False
    anchor_name: str = "未知主播"
    session_title: str = "未命名直播场次"
    live_start_time: datetime | None = None
    live_duration_seconds: int = 0
    segment_count: int = 0
    error_message: str | None = None
    postprocess_status: str = "skipped"
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
    # 转写进度（音频分片维度，从 asr_audio_chunks 表统计）
    total_chunks: int = 0  # 音频分片总数（进度分母）
    completed_chunks: int = 0  # 已完成音频分片数（进度分子）
    progress_percent: int = 0  # 转写进度百分比 0-100


# ── 分段 / 全文 ──


class TranscriptComplianceHit(BaseModel):
    """关键词命中仅表示涉嫌违规，必须人工复核。"""

    rule_code: str
    name: str
    category: str
    matched_keyword: str
    severity: str = "warning"
    guidance: str
    review_status: Literal["suspected"] = "suspected"


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
    compliance_hits: list[TranscriptComplianceHit] = Field(default_factory=list)


class TranscriptTaskDeleteResponse(BaseModel):
    """DELETE /transcripts/tasks/{task_id}"""

    task_id: int
    deleted: bool = True
    message: str = ""


class TranscriptTaskActionResponse(BaseModel):
    """单任务停止、重试或取消人工优先的统一结果。"""

    task_id: int
    status: str
    queue_source: Literal["auto", "manual"] = "auto"
    message: str


class TranscriptFailedClearResponse(BaseModel):
    """DELETE /transcripts/tasks/failed"""

    deleted_count: int = 0
    message: str = ""


class TranscriptFullTextResponse(BaseModel):
    """GET /transcripts/{session_id}/full-text"""

    id: int | None = None
    full_text: str = ""
    available: bool = False
