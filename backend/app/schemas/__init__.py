"""Pydantic 数据模型 - 请求/响应"""
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel


# ===== 直播间 =====
class LiveRoomBase(BaseModel):
    account_name: str
    anchor_name: str
    douyin_id: Optional[str] = None
    room_id_str: Optional[str] = None
    team_name: Optional[str] = None
    platform: str = "douyin"
    status: bool = True


class LiveRoomCreate(LiveRoomBase):
    pass


class LiveRoomUpdate(BaseModel):
    account_name: Optional[str] = None
    anchor_name: Optional[str] = None
    douyin_id: Optional[str] = None
    team_name: Optional[str] = None
    status: Optional[bool] = None


class LiveRoomResponse(LiveRoomBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ===== 直播场次 =====
class LiveSessionBase(BaseModel):
    room_id: int
    session_title: Optional[str] = None
    dashboard_url: Optional[str] = None
    stream_url: Optional[str] = None
    live_start_time: Optional[datetime] = None
    live_end_time: Optional[datetime] = None
    live_status: str = "ended"


class LiveSessionCreate(LiveSessionBase):
    pass


class LiveSessionUpdate(BaseModel):
    session_title: Optional[str] = None
    live_end_time: Optional[datetime] = None
    live_duration_seconds: Optional[int] = None
    live_status: Optional[str] = None
    total_viewers: Optional[int] = None
    peak_online_count: Optional[int] = None
    leads_count: Optional[int] = None


class LiveSessionResponse(LiveSessionBase):
    id: int
    anchor_name: Optional[str] = None  # 从 LiveRoom 关联获取
    live_duration_seconds: int = 0
    total_viewers: int = 0
    avg_watch_seconds: float = 0
    peak_online_count: int = 0
    realtime_online_count: int = 0
    ad_cost: float = 0
    new_followers: int = 0
    exposure_enter_rate: float = 0
    comment_rate: float = 0
    interaction_rate: float = 0
    comments_count: int = 0
    leads_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LiveMetricDetailResponse(BaseModel):
    """直播大屏的单个时间点指标。"""

    metric_time: datetime
    exposure_count: int = 0
    online_count: int = 0
    enter_count: int = 0
    enter_fans_count: int = 0
    leave_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    follow_count: int = 0
    natural_traffic_count: int = 0
    marketing_traffic_count: int = 0


class LiveSessionDetailResponse(BaseModel):
    """直播场次详情页需要的完整采集结果。"""

    session: LiveSessionResponse
    metrics: list[LiveMetricDetailResponse]
    comments: list["CommentResponse"]
    stream_url: Optional[str] = None
    stream_source_count: int = 0


# ===== 评论 =====
class CommentBase(BaseModel):
    session_id: int
    user_nickname: Optional[str] = None
    comment_content: Optional[str] = None
    comment_time: Optional[datetime] = None
    is_high_intent: int = 0
    sentiment: Optional[str] = None
    keywords: Optional[str] = None


class CommentCreate(CommentBase):
    pass


class CommentResponse(CommentBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


LiveSessionDetailResponse.model_rebuild()


# ===== 话术分段 =====
class TranscriptSegmentBase(BaseModel):
    session_id: int
    segment_start: Optional[float] = None
    segment_end: Optional[float] = None
    text_content: Optional[str] = None
    segment_type: Optional[str] = None
    asr_status: str = "pending"


class TranscriptSegmentCreate(TranscriptSegmentBase):
    pass


class TranscriptSegmentResponse(TranscriptSegmentBase):
    id: int
    ai_score: Optional[float] = None
    is_high_conversion: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


# ===== 留资 =====
class LeadBase(BaseModel):
    session_id: int
    lead_name: Optional[str] = None
    lead_phone: Optional[str] = None
    lead_source: Optional[str] = None
    is_valid: int = 1
    create_time: Optional[datetime] = None


class LeadCreate(LeadBase):
    pass


class LeadResponse(LeadBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ===== 知识库 =====
class KnowledgeBaseBase(BaseModel):
    session_id: Optional[int] = None
    category: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    source_type: Optional[str] = None


class KnowledgeBaseCreate(KnowledgeBaseBase):
    pass


class KnowledgeBaseResponse(KnowledgeBaseBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ===== AI 分析报告 =====
class AnalysisReportBase(BaseModel):
    session_id: int
    report_type: str
    report_title: Optional[str] = None
    summary: Optional[str] = None


class AnalysisReportCreate(AnalysisReportBase):
    report_content: Optional[dict] = None


class AnalysisReportResponse(AnalysisReportBase):
    id: int
    report_content: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True
