"""知识库 & 排班 — Pydantic 响应模型"""

from datetime import datetime
from pydantic import BaseModel, Field


# ── 知识库 ──

class KnowledgePageResponse(BaseModel):
    """GET /knowledge-base/page"""
    records: list[dict] = Field(default_factory=list)
    total: int = 0
    current: int = 1
    size: int = 10


class KnowledgeTimeSliceStatusResponse(BaseModel):
    """GET /knowledge-base/time-slices/status"""
    slice_count: int = 0
    session_count: int = 0
    transcript_slice_count: int = 0
    comment_slice_count: int = 0
    metric_slice_count: int = 0
    high_intent_slice_count: int = 0
    unmapped_comment_count: int = 0
    knowledge_item_count: int = 0
    latest_updated_at: datetime | None = None
    slice_seconds: int = 60
    parser_version: str = "time-slice-v1"


class KnowledgeTimeSliceSearchResponse(BaseModel):
    """GET /knowledge-base/time-slices/search"""
    results: list[dict] = Field(default_factory=list)
    total: int = 0


class KnowledgeTimeSliceSyncResponse(BaseModel):
    """POST /knowledge-base/time-slices/sync/{session_id}"""
    status: str = "ok"
    session_id: int | None = None
    time_slices_created: int = 0
    time_slices_updated: int = 0
    time_slices_unchanged: int = 0
    unmapped_comments: int = 0


class KnowledgeDeleteResponse(BaseModel):
    """DELETE /knowledge-base/{kb_id}"""
    message: str = ""


# ── 主播排班 ──

class AnchorScheduleDayItem(BaseModel):
    anchor_name: str = ""
    start_time: str | None = None
    end_time: str | None = None
    session_id: int | None = None
    status: str = ""
    status_label: str = ""
    duration_seconds: int | None = None


class AnchorScheduleCompletion(BaseModel):
    anchor_name: str = ""
    planned_count: int = 0
    actual_count: int = 0
    missing_count: int = 0
    invalid_count: int = 0
    extra_count: int = 0
    completion_rate: float = 0


class AnchorScheduleDashboardResponse(BaseModel):
    """GET /anchor-schedules/dashboard"""
    schedule_date: str = ""
    anchor_count: int = 0
    planned_count: int = 0
    actual_count: int = 0
    completions: list[dict] = Field(default_factory=list)
    details: list[dict] = Field(default_factory=list)
