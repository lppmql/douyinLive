"""Pydantic 数据模型 - 请求/响应"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.core.status import TaskStatus


# ===== 通用响应 =====
class MessageResponse(BaseModel):
    """通用消息响应，用于 DELETE 等简单操作"""
    message: str = "操作成功"


# ===== 直播间 =====
class LiveRoomBase(BaseModel):
    account_name: str = Field(min_length=1, max_length=200, description="账号名称")
    anchor_name: str = Field(min_length=1, max_length=200, description="主播名称")
    anchor_nickname: Optional[str] = Field(default=None, max_length=200, description="主播昵称")
    anchor_avatar_url: Optional[str] = Field(default=None, max_length=500, description="头像 URL")
    douyin_id: Optional[str] = Field(default=None, max_length=200, description="抖音 ID")
    douyin_uid: Optional[str] = Field(default=None, max_length=200, description="抖音 UID")
    room_id_str: Optional[str] = Field(default=None, max_length=200, description="直播间 ID 字符串")
    team_name: Optional[str] = Field(default=None, max_length=200, description="团队名称")
    platform: str = Field(default="douyin", max_length=50, description="平台")
    status: bool = True


class LiveRoomCreate(LiveRoomBase):
    pass


class LiveRoomUpdate(BaseModel):
    account_name: Optional[str] = None
    anchor_name: Optional[str] = None
    anchor_nickname: Optional[str] = None
    anchor_avatar_url: Optional[str] = None
    douyin_id: Optional[str] = None
    douyin_uid: Optional[str] = None
    team_name: Optional[str] = None
    status: Optional[bool] = None


class LiveRoomResponse(LiveRoomBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime

# ===== 直播场次 =====
class LiveSessionBase(BaseModel):
    room_id: int = Field(gt=0, description="直播间 ID")
    session_title: Optional[str] = Field(default=None, max_length=500, description="场次标题")
    dashboard_url: Optional[str] = Field(default=None, max_length=1000, description="大屏 URL")
    stream_url: Optional[str] = Field(default=None, max_length=1000, description="流地址")
    live_start_time: Optional[datetime] = None
    live_end_time: Optional[datetime] = None
    live_status: str = Field(default="ended", max_length=50, description="直播状态")


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


class LiveSessionListItemResponse(BaseModel):
    """直播场次列表的轻量字段，避免分页时序列化完整详情。"""

    id: int
    anchor_name: Optional[str] = None
    anchor_nickname: Optional[str] = None
    anchor_avatar_url: Optional[str] = None
    douyin_id: Optional[str] = None
    session_title: Optional[str] = None
    detail_collection_status: str = TaskStatus.PENDING
    detail_collection_error: Optional[str] = None
    live_start_time: Optional[datetime] = None
    live_end_time: Optional[datetime] = None
    live_duration_seconds: int = 0
    live_status: str = "ended"
    peak_online_count: int = 0
    new_followers: int = 0
    comments_count: int = 0
    leads_count: int = 0


class LiveSessionPageResponse(BaseModel):
    records: list[LiveSessionListItemResponse]
    total: int
    current: int
    size: int


class LiveSessionResponse(LiveSessionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    anchor_name: Optional[str] = None
    anchor_nickname: Optional[str] = None
    anchor_avatar_url: Optional[str] = None
    douyin_id: Optional[str] = None
    douyin_uid: Optional[str] = None
    detail_collection_status: str = TaskStatus.PENDING
    detail_collection_error: Optional[str] = None
    live_duration_seconds: int = 0
    total_viewers: int = 0
    viewed_count: int = 0
    avg_online_count: int = 0
    avg_watch_seconds: float = 0
    fans_avg_watch_seconds: float = 0
    peak_online_count: int = 0
    realtime_online_count: int = 0
    private_message_count: int = 0
    private_message_longterm_count: int = 0
    scene_leads_count: int = 0
    ad_cost: float = 0
    mini_windmill_click_count: int = 0
    mini_windmill_click_rate: float = 0
    card_click_count: int = 0
    card_click_rate: float = 0
    new_followers: int = 0
    follow_rate: float = 0
    share_count: int = 0
    share_users: int = 0
    like_count: int = 0
    like_users: int = 0
    comment_users: int = 0
    interaction_count: int = 0
    interaction_users: int = 0
    watch_count: int = 0
    watch_over_1m_count: int = 0
    fans_club_join_count: int = 0
    fans_club_join_rate: float = 0
    gift_count: int = 0
    gift_amount: float = 0
    dislike_count: int = 0
    dislike_users: int = 0
    wechat_add_count: int = 0
    wechat_add_cost: float = 0
    form_submit_count: int = 0
    form_submit_users: int = 0
    form_submit_cost: float = 0
    exposure_enter_rate: float = 0
    fans_view_ratio: float = 0
    scene_lead_conversion_rate: float = 0
    share_rate: float = 0
    like_rate: float = 0
    comment_rate: float = 0
    interaction_rate: float = 0
    natural_traffic_ratio: float = 0
    marketing_traffic_ratio: float = 0
    other_traffic_ratio: float = 0
    live_exposure_users: int = 0
    live_enter_users: int = 0
    card_click_users: int = 0
    comments_count: int = 0
    leads_count: int = 0
    created_at: datetime
    updated_at: datetime

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
    clue_count: int = 0
    windmill_click_count: int = 0
    card_click_count: int = 0
    wechat_add_count: int = 0
    form_submit_count: int = 0
    form_submit_users: int = 0
    cost_amount: float = 0
    natural_traffic_count: int = 0
    marketing_traffic_count: int = 0


class LiveAudienceProfileResponse(BaseModel):
    """单场直播的观众画像分布。"""

    model_config = ConfigDict(from_attributes=True)

    dimension_type: str
    dimension_name: str
    ratio: float = 0
    count: int = 0


class TranscriptQualityResponse(BaseModel):
    """话术覆盖完整度与真实语速。"""

    status: str
    coverage_percent: Optional[float] = None
    covered_seconds: float = 0
    duration_seconds: float = 0
    missing_ranges: list[tuple[float, float]] = Field(default_factory=list)
    speech_char_count: int = 0
    speech_seconds: float = 0
    speech_rate_cpm: Optional[int] = None
    rate_source: str = "realtime_estimate"


class ConversionSummaryResponse(BaseModel):
    """整场钩子与客资转化摘要。"""

    hook_count: int = 0
    effective_hook_count: int = 0
    strong_hook_count: int = 0
    incomplete_hook_count: int = 0
    session_lead_count: int = 0
    hook_window_lead_count: int = 0
    exact_matched_user_count: int = 0
    comment_user_count: int = 0


class HookEventResponse(BaseModel):
    """由真实主播转写识别出的钩子事件。"""

    id: int
    start_seconds: float = 0
    end_seconds: float = 0
    hook_types: list[str] = Field(default_factory=list)
    is_formal_hook: bool = False
    stage: str
    strength: str
    missing_elements: list[str] = Field(default_factory=list)
    evidence_text: str
    related_lead_count: int = 0
    comment_after_5m: int = 0
    comment_after_15m: int = 0
    comment_after_30m: int = 0
    lead_after_5m: int = 0
    lead_after_15m: int = 0
    lead_after_30m: int = 0
    high_intent_user_count: int = 0
    attribution_label: str


class AudienceCommentResponse(BaseModel):
    id: int
    content: str
    comment_time: Optional[datetime] = None


class AudienceUserInsightResponse(BaseModel):
    """按稳定用户标识聚合的评论、留资与主播承接分析。"""

    identity_key: str
    user_nickname: Optional[str] = None
    user_avatar_comment_id: Optional[int] = None
    user_douyin_id: Optional[str] = None
    user_unique_id: Optional[str] = None
    user_short_id: Optional[str] = None
    douyin_id_type: Optional[str] = None
    profile_status: str
    comment_count: int = 0
    comments: list[AudienceCommentResponse] = Field(default_factory=list)
    intent_topics: list[str] = Field(default_factory=list)
    intent_level: str = "low"
    has_lead: bool = False
    lead_match_method: Optional[str] = None
    lead_time: Optional[datetime] = None
    host_responded: bool = False
    hook_action_detected: bool = False
    host_evidence: Optional[str] = None
    related_hook_ids: list[int] = Field(default_factory=list)
    recommendation: str


class SessionDataCoverageResponse(BaseModel):
    comment_count: int = 0
    analysis_comment_count: int = 0
    analysis_truncated: bool = False
    comment_user_count: int = 0
    avatar_user_count: int = 0
    douyin_id_user_count: int = 0
    transcript_segment_count: int = 0
    session_lead_count: int = 0
    avatar_coverage_percent: float = 0
    douyin_id_coverage_percent: float = 0
    profile_enrichment_status: str = "idle"
    profile_enrichment_completed: int = 0
    profile_enrichment_total: int = 0


class CommentProfileEnrichmentStatusResponse(BaseModel):
    """评论用户公开资料补全队列状态，不包含 Cookie 或用户身份明文。"""

    status: str = "idle"
    scope: Optional[str] = None
    total: int = 0
    completed: int = 0
    success: int = 0
    partial: int = 0
    failed: int = 0
    message: str = ""
    configured: bool = False
    cookie_file_secure: bool = False
    fingerprint_configured: bool = False
    batch_size: int = 0
    request_interval_seconds: float = 0
    cooldown_seconds: int = 0


class LiveSessionDetailResponse(BaseModel):
    """直播场次详情页需要的完整采集结果。"""

    session: LiveSessionResponse
    metrics: list[LiveMetricDetailResponse]
    comments: list["CommentResponse"]
    profiles: list[LiveAudienceProfileResponse]
    stream_url: Optional[str] = None
    stream_source_count: int = 0
    transcript_quality: TranscriptQualityResponse
    conversion_summary: ConversionSummaryResponse
    hook_events: list[HookEventResponse] = Field(default_factory=list)
    audience_users: list[AudienceUserInsightResponse] = Field(default_factory=list)
    data_coverage: SessionDataCoverageResponse


# ===== 评论 =====
class CommentBase(BaseModel):
    session_id: int = Field(gt=0, description="场次 ID")
    user_nickname: Optional[str] = Field(default=None, max_length=200, description="用户昵称")
    user_avatar_url: Optional[str] = Field(default=None, max_length=1000, description="用户头像 URL")
    user_douyin_id: Optional[str] = Field(default=None, max_length=100, description="用户公开抖音号")
    user_sec_uid: Optional[str] = Field(default=None, max_length=200, description="用户 sec_uid")
    webcast_uid: Optional[str] = Field(default=None, max_length=200, description="直播间 UID")
    comment_content: Optional[str] = Field(default=None, max_length=5000, description="评论内容")
    comment_time: Optional[datetime] = None
    is_high_intent: int = Field(default=0, ge=0, le=1, description="是否高意向")
    sentiment: Optional[str] = Field(default=None, max_length=50, description="情感倾向")
    keywords: Optional[str] = Field(default=None, max_length=500, description="关键词")


class CommentCreate(CommentBase):
    pass


class CommentResponse(CommentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime

LiveSessionDetailResponse.model_rebuild()


# ===== 话术分段 =====
class TranscriptSegmentBase(BaseModel):
    session_id: int = Field(gt=0, description="场次 ID")
    segment_start: Optional[float] = Field(default=None, ge=0, description="开始秒数")
    segment_end: Optional[float] = Field(default=None, ge=0, description="结束秒数")
    text_content: Optional[str] = Field(default=None, max_length=10000, description="文本内容")
    segment_type: Optional[str] = Field(default=None, max_length=100, description="分段类型")
    asr_status: str = Field(default=TaskStatus.PENDING, max_length=50, description="ASR 状态")


class TranscriptSegmentCreate(TranscriptSegmentBase):
    pass


class TranscriptSegmentResponse(TranscriptSegmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ai_score: Optional[float] = None
    is_high_conversion: int = 0
    created_at: datetime

# ===== 留资 =====
class LeadBase(BaseModel):
    session_id: Optional[int] = Field(default=None, gt=0, description="真实归属场次 ID")
    lead_name: Optional[str] = Field(default=None, max_length=200, description="留资姓名")
    lead_phone: Optional[str] = Field(default=None, max_length=30, description="留资电话")
    douyin_id: Optional[str] = Field(default=None, max_length=100, description="客户抖音号")
    anchor_name: Optional[str] = Field(default=None, max_length=100, description="客资记录的主播")
    lead_source: Optional[str] = Field(default=None, max_length=200, description="留资来源")
    external_source: Optional[str] = Field(default=None, max_length=50, description="外部来源系统")
    external_id: Optional[int] = Field(default=None, gt=0, description="外部来源唯一编号")
    attribution_status: str = Field(default="matched", max_length=20, description="场次归属状态")
    is_valid: int = Field(default=1, ge=0, le=1, description="是否有效")
    remark: Optional[str] = Field(default=None, max_length=500, description="备注")
    create_time: Optional[datetime] = None


class LeadCreate(BaseModel):
    """人工新增客资只接收业务字段，外部来源编号只能由可信同步服务写入。"""

    model_config = ConfigDict(extra="forbid")

    session_id: int = Field(gt=0, description="真实归属场次 ID")
    lead_name: Optional[str] = Field(default=None, max_length=200, description="留资姓名")
    lead_phone: Optional[str] = Field(default=None, max_length=30, description="留资电话")
    douyin_id: Optional[str] = Field(default=None, max_length=100, description="客户抖音号")
    anchor_name: Optional[str] = Field(default=None, max_length=100, description="客资记录的主播")
    lead_source: Optional[str] = Field(default=None, max_length=200, description="留资来源")
    is_valid: int = Field(default=1, ge=0, le=1, description="是否有效")
    remark: Optional[str] = Field(default=None, max_length=500, description="备注")
    create_time: Optional[datetime] = None


class LeadResponse(LeadBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime

# ===== 知识库 =====
class KnowledgeBaseBase(BaseModel):
    session_id: Optional[int] = Field(default=None, gt=0, description="场次 ID")
    category: Optional[str] = Field(default=None, max_length=200, description="分类")
    title: Optional[str] = Field(default=None, max_length=500, description="标题")
    content: Optional[str] = Field(default=None, max_length=50000, description="内容")
    source_type: Optional[str] = Field(default=None, max_length=100, description="来源类型")


class KnowledgeBaseCreate(KnowledgeBaseBase):
    pass


class KnowledgeBaseResponse(KnowledgeBaseBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime

# ===== AI 分析报告 =====
class AnalysisReportBase(BaseModel):
    session_id: int = Field(gt=0, description="场次 ID")
    report_type: str = Field(min_length=1, max_length=100, description="报告类型")
    report_title: Optional[str] = Field(default=None, max_length=500, description="报告标题")
    summary: Optional[str] = Field(default=None, max_length=5000, description="摘要")


class AnalysisReportCreate(AnalysisReportBase):
    report_content: Optional[dict] = None


class AnalysisReportResponse(AnalysisReportBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    report_content: Optional[dict] = None
    created_at: datetime
