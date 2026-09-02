"""客资列表和增量同步接口结构。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LeadSyncResponse(BaseModel):
    """一次同步执行结果。"""

    success: bool
    added_count: int = 0
    duplicate_count: int = 0
    matched_count: int = 0
    pending_count: int = 0
    last_external_id: int = 0
    page_count: int = 0
    paired_count: int = 0
    sanitized_douyin_id_count: int = 0
    rematch: dict | None = None  # 仅 ?rematch=true 时返回重匹配统计


class LeadSyncStatusResponse(BaseModel):
    """前端状态卡所需信息，不返回手机号或抖音号。"""

    configured: bool
    source_system: str = "kezi"
    status: str = "not_configured"
    last_external_id: int = 0
    last_synced_at: datetime | None = None
    last_error: str | None = None
    synced_count: int = 0
    duplicate_count: int = 0
    pending_count: int = 0
    interval_seconds: int


class LeadAttributionUpdate(BaseModel):
    """人工把待归属客资绑定到真实场次。"""

    session_id: int = Field(gt=0, description="要绑定的真实直播场次 ID")


class LeadPairAttributionUpdate(BaseModel):
    """人工确认一组“抖音号 + 联系方式”所属场次。"""

    session_id: int = Field(gt=0)


class LeadPairPendingResponse(BaseModel):
    id: int
    anchor_name: str
    douyin_id: str
    contact_type: str
    contact_value: str
    converted_at: datetime
    gap_seconds: int
    candidate_sessions: list[dict] = Field(default_factory=list)


class LeadDetailResponse(BaseModel):
    """客资详情；接口本身已有登录鉴权，页面仍应按需展示。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int | None
    lead_name: str | None
    lead_phone: str | None
    douyin_id: str | None
    anchor_name: str | None
    lead_source: str | None
    external_source: str | None
    external_id: int | None
    attribution_status: str
    is_valid: int
    remark: str | None
    create_time: datetime | None
    created_at: datetime
