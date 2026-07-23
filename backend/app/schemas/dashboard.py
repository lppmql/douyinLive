"""仪表盘 & DataEase — Pydantic 响应模型"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DashboardSummaryResponse(BaseModel):
    """GET /dashboard/summary"""
    anchor_count: int = 0
    session_count: int = 0
    live_session_count: int = 0
    detail_complete_count: int = 0
    detail_completion_rate: float = 0
    total_viewers: int = 0
    total_comments: int = 0
    high_intent_comment_count: int = 0
    total_private_messages: int = 0
    total_leads: int = 0
    total_ad_cost: float = 0
    average_lead_cost: float = 0
    open_review_action_count: int = 0


class AnchorSummaryItem(BaseModel):
    """按主播分组的经营指标"""
    douyin_id: str = ""
    anchor_name: str = ""
    anchor_avatar_url: str = ""
    anchor_avatar_session_id: int | None = None
    session_count: int = 0
    total_viewers: int = 0
    total_comments: int = 0
    total_private_messages: int = 0
    total_leads: int = 0
    total_ad_cost: float = 0
    total_interactions: int = 0
    total_new_followers: int = 0


class AnchorSummaryResponse(BaseModel):
    """GET /dashboard/summary/by-anchor"""
    anchors: list[AnchorSummaryItem] = Field(default_factory=list)
    total: dict[str, Any] = Field(default_factory=dict)


class DataEaseStatusResponse(BaseModel):
    """GET /dataease/status"""
    source_session_count: int = 0
    synced_session_count: int = 0
    pending_session_count: int = 0
    outdated_session_count: int = 0
    coverage_rate: float = 100.0
    metric_row_count: int = 0
    profile_row_count: int = 0
    comment_summary_count: int = 0
    transcript_summary_count: int = 0
    ai_summary_count: int = 0
    last_synced_at: datetime | None = None


class DataEaseSemanticResponse(BaseModel):
    """GET /dataease/semantic-layer"""
    version: str = "semantic-v1"
    metrics: list[dict] = []
    datasets: list[dict] = []
    time_policy: dict = {}
    dataease_access: str = ""


class DataEaseSyncResponse(BaseModel):
    """POST /dataease/sync"""
    status: str = "ok"
    selected_count: int = 0
    synced_count: int = 0
    failed_count: int = 0
    errors: list[str] = Field(default_factory=list)
    removed_stale_row_count: int = 0
    dataease: DataEaseStatusResponse | None = None
