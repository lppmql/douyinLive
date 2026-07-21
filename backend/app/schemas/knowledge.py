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
    """GET /anchor-schedules/dashboard

    直接映射 build_schedule_dashboard / build_schedule_range_dashboard
    返回的字典结构。字段用宽松类型避免 Pydantic 过滤掉 Service 返回的
    嵌套数据（actual_session 可能为 None、extra 标记等条件字段）。
    """
    schedule_date: str = ""
    start_date: str = ""
    end_date: str = ""
    day_count: int = 0
    generated_at: str = ""
    source_name: str = ""
    rule: dict = Field(default_factory=dict)
    summary: dict = Field(default_factory=dict)
    anchors: list[dict] = Field(default_factory=list)
    rows: list[dict] = Field(default_factory=list)
    reminders: list[dict] = Field(default_factory=list)
