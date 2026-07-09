"""Phase 3: 采集相关 Pydantic 数据模型"""
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel


# ===== 采集账号 =====
class ScraperAccountBase(BaseModel):
    account_name: Optional[str] = None
    douyin_id: Optional[str] = None
    login_status: str = "never"


class ScraperAccountCreate(ScraperAccountBase):
    pass


class ScraperAccountUpdate(BaseModel):
    account_name: Optional[str] = None
    douyin_id: Optional[str] = None
    login_status: Optional[str] = None
    expires_at: Optional[datetime] = None


class ScraperAccountResponse(ScraperAccountBase):
    id: int
    storage_state_path: Optional[str] = None
    user_agent: Optional[str] = None
    viewport_width: Optional[int] = None
    viewport_height: Optional[int] = None
    expires_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ===== 采集任务 =====
class ScraperTaskBase(BaseModel):
    account_id: Optional[int] = None
    session_id: Optional[int] = None
    task_type: str
    status: str = "pending"


class ScraperTaskCreate(ScraperTaskBase):
    pass


class ScraperTaskResponse(ScraperTaskBase):
    id: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ===== 采集日志 =====
class ScraperLogBase(BaseModel):
    task_id: Optional[int] = None
    level: str = "info"
    message: Optional[str] = None


class ScraperLogResponse(ScraperLogBase):
    id: int
    raw_json: Optional[Any] = None
    created_at: datetime

    class Config:
        from_attributes = True


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
