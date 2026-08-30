"""原生经营仪表盘响应模型。"""

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
    private_message_rate: float = 0
    lead_conversion_rate: float = 0
    total_exposure_users: int = 0
    total_enter_users: int = 0
    total_card_click_users: int = 0
    open_review_action_count: int = 0


class AnchorSummaryItem(BaseModel):
    """按主播分组的经营指标"""
    anchor_key: str = ""
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


class DashboardTrendPoint(BaseModel):
    """原生大屏按自然日汇总的趋势点。"""

    date_key: str
    session_count: int = 0
    total_viewers: int = 0
    total_comments: int = 0
    total_private_messages: int = 0
    total_leads: int = 0
    total_ad_cost: float = 0


class DashboardFunnelStep(BaseModel):
    """从曝光到确认留资的漏斗步骤。"""

    label: str
    value: int = 0
    step_rate: float = 0


class DashboardSessionItem(BaseModel):
    """原生大屏最近场次经营明细。"""

    id: int
    anchor_name: str = ""
    anchor_avatar_url: str = ""
    douyin_id: str = ""
    session_title: str = ""
    live_start_time: datetime | None = None
    live_duration_seconds: int = 0
    total_viewers: int = 0
    total_comments: int = 0
    total_private_messages: int = 0
    total_leads: int = 0
    total_ad_cost: float = 0
    lead_cost: float = 0


class DashboardOperationsResponse(BaseModel):
    """SoybeanAdmin 原生经营大屏的一次性响应。"""

    summary: DashboardSummaryResponse
    anchors: list[AnchorSummaryItem] = Field(default_factory=list)
    trend: list[DashboardTrendPoint] = Field(default_factory=list)
    funnel: list[DashboardFunnelStep] = Field(default_factory=list)
    recent_sessions: list[DashboardSessionItem] = Field(default_factory=list)
