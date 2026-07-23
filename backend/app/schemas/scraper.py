"""Phase 3: 采集相关 Pydantic 数据模型"""
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.core.status import TaskStatus


# ===== 采集账号 =====
class ScraperAccountBase(BaseModel):
    account_name: Optional[str] = None
    douyin_nickname: Optional[str] = None
    douyin_id: Optional[str] = None
    login_status: str = "never"


class ScraperAccountCreate(ScraperAccountBase):
    pass


class ScraperAccountUpdate(BaseModel):
    account_name: Optional[str] = None
    douyin_nickname: Optional[str] = None
    douyin_id: Optional[str] = None
    login_status: Optional[str] = None
    expires_at: Optional[datetime] = None


class ScraperAccountResponse(ScraperAccountBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    viewport_width: Optional[int] = None
    viewport_height: Optional[int] = None
    cookie_saved: bool = False
    cookie_status: str = "missing"
    fingerprint_saved: bool = False
    expires_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    cookie_checked_at: Optional[datetime] = None
    cookie_refreshed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

# ===== 采集任务 =====
class ScraperTaskBase(BaseModel):
    account_id: Optional[int] = None
    session_id: Optional[int] = None
    task_type: str
    status: str = TaskStatus.PENDING


class ScraperTaskCreate(ScraperTaskBase):
    pass


class ScraperTaskResponse(ScraperTaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    cancel_requested_at: Optional[datetime] = None
    retry_of_task_id: Optional[int] = None
    task_options_json: Optional[dict[str, Any]] = None
    result_json: Optional[dict[str, Any]] = None
    idempotency_key: Optional[str] = None
    trace_id: Optional[str] = None
    worker_id: Optional[str] = None
    heartbeat_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 2
    priority: int = 50
    progress_percent: int = 0
    progress_current: int = 0
    progress_total: int = 0
    progress_stage: Optional[str] = None
    progress_message: Optional[str] = None
    collected_anchor_count: int = 0
    collected_session_count: int = 0
    new_session_count: int = 0
    mapped_session_count: int = 0
    checked_detail_count: int = 0
    refreshed_detail_count: int = 0
    failed_detail_count: int = 0
    remaining_detail_count: int = 0
    created_at: datetime

    @field_validator("retry_count", "max_retries", "priority", mode="before")
    @classmethod
    def normalize_runtime_defaults(cls, value, info):
        if value is not None:
            return value
        return {"retry_count": 0, "max_retries": 2, "priority": 50}[info.field_name]

# ===== 采集日志 =====
class ScraperLogBase(BaseModel):
    task_id: Optional[int] = None
    level: str = "info"
    message: Optional[str] = None


class ScraperLogResponse(ScraperLogBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    raw_json: Optional[Any] = None
    session_id: Optional[int] = None
    anchor_name: Optional[str] = None
    anchor_nickname: Optional[str] = None
    anchor_avatar_url: Optional[str] = None
    douyin_id: Optional[str] = None
    session_title: Optional[str] = None
    live_start_time: Optional[datetime] = None
    room_id_str: Optional[str] = None
    task_type: Optional[str] = None
    event_type: Optional[str] = None
    stage: Optional[str] = None
    data_details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

# ===== 采集器状态 =====
class CollectorStatusResponse(BaseModel):
    connected: bool = False
    active_task_count: int = 0
    default_account: Optional[ScraperAccountResponse] = None


# ===== 登录流程 =====
class LoginStartResponse(BaseModel):
    task_id: int
    message: str


class LoginQRResponse(BaseModel):
    qr_code_base64: str


class LoginStatusResponse(BaseModel):
    status: str  # pending / scanning / success / failed / timeout
    account: Optional[ScraperAccountResponse] = None
    message: str = ""


class AccountHealthResponse(BaseModel):
    account_id: int
    valid: bool
    login_status: str
    cookie_status: str
    douyin_nickname: Optional[str] = None
    douyin_id: Optional[str] = None
    checked_at: datetime
    message: str


class AsrControlResponse(BaseModel):
    enabled: bool
    engine_running: bool
    worker_running: bool
    queued_count: int = 0
    processing_count: int = 0
    postprocess_pending_count: int = 0
    postprocess_processing_count: int = 0
    postprocess_completed_count: int = 0
    postprocess_failed_count: int = 0
    message: str = ""


# ===== 刷新数据采集结果 =====
class CollectRoomResult(BaseModel):
    room_id: str = ""
    anchor_name: str = ""
    anchor_nickname: str = ""
    douyin_id: str = ""
    is_live: bool = False
    metrics_count: int = 0
    comments_count: int = 0
    profiles_count: int = 0
    session_id: Optional[int] = None
    error: Optional[str] = None


class CollectAllResponse(BaseModel):
    total_rooms: int = 0
    collected_rooms: int = 0
    history_synced_count: int = 0
    enterprise_anchor_count: int = 0
    enterprise_session_synced_count: int = 0
    enterprise_session_discovered_count: int = 0
    anchor_profile_synced_count: int = 0
    unmapped_session_pruned_count: int = 0
    history_detail_synced_count: int = 0
    history_detail_checked_count: int = 0
    history_detail_remaining_count: int = 0
    history_detail_batch_size: int = 0
    history_detail_failed_count: int = 0
    dataease_synced_count: int = 0
    dataease_failed_count: int = 0
    asr_queued_count: int = 0
    asr_active_count: int = 0
    asr_queue_capacity: int = 0
    postprocess_pending_count: int = 0
    postprocess_processing_count: int = 0
    postprocess_completed_count: int = 0
    postprocess_failed_count: int = 0
    results: list[CollectRoomResult] = Field(default_factory=list)
    message: Optional[str] = None


class AccountDeleteResponse(BaseModel):
    """删除采集账号的响应"""
    message: str
    detached_task_count: int = 0


class LogsClearResponse(BaseModel):
    """清空采集日志的响应"""
    message: str
    deleted_count: int = 0


# ===== 采集控制中心 =====
class CollectorModuleStatus(BaseModel):
    """一个开关模块的真实状态，前端不需要再拼装多套状态接口。"""

    key: str
    label: str
    mode: str
    enabled: bool = False
    running: bool = False
    status: str = "idle"
    pending_count: int = 0
    processing_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    summary: str = ""
    disabled_reason: str = ""
    interval_seconds: int = 0
    enabled_at: Optional[datetime] = None
    last_scheduled_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None


class ResourceComponentUsage(BaseModel):
    """本项目一个进程或容器的真实资源占用。"""

    key: str
    label: str
    running: bool = False
    cpu_percent: float = 0
    memory_bytes: int = 0


class ComputerResourceUsage(BaseModel):
    """数据采集页使用的电脑资源快照。"""

    sampled_at: datetime
    cpu_percent: float = 0
    memory_percent: float = 0
    memory_used_bytes: int = 0
    memory_total_bytes: int = 0
    disk_used_percent: float = 0
    disk_free_bytes: int = 0
    app_memory_bytes: int = 0
    pressure_level: str = "normal"
    pressure_message: str = ""
    components: list[ResourceComponentUsage] = Field(default_factory=list)


class UnifiedTaskResponse(BaseModel):
    """采集任务和 ASR 任务在任务抽屉中的统一展示结构。"""

    task_key: str
    source: str
    id: int
    module_key: str
    task_type: str
    task_label: str
    status: str
    progress_percent: int = 0
    progress_current: int = 0
    progress_total: int = 0
    progress_stage: Optional[str] = None
    progress_message: Optional[str] = None
    account_id: Optional[int] = None
    session_id: Optional[int] = None
    anchor_name: Optional[str] = None
    session_title: Optional[str] = None
    error_message: Optional[str] = None
    trace_id: Optional[str] = None
    worker_id: Optional[str] = None
    heartbeat_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 0
    retry_of_task_id: Optional[int] = None
    can_stop: bool = False
    can_retry: bool = False
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result_json: Optional[dict[str, Any]] = None
    collected_anchor_count: int = 0
    collected_session_count: int = 0
    new_session_count: int = 0
    checked_detail_count: int = 0
    refreshed_detail_count: int = 0
    failed_detail_count: int = 0
    remaining_detail_count: int = 0


class CollectorControlCenterResponse(BaseModel):
    modules: list[CollectorModuleStatus]
    current_task: Optional[UnifiedTaskResponse] = None
    active_task_count: int = 0
    queued_task_count: int = 0
    latest_task: Optional[UnifiedTaskResponse] = None
    resource_usage: ComputerResourceUsage


class CollectorTaskActionResponse(BaseModel):
    success: bool
    message: str
    task: Optional[UnifiedTaskResponse] = None
