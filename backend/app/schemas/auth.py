"""认证相关 Pydantic 模型 — 登录 / 用户信息 / 用户管理"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ===== 登录认证 =====

class LoginRequest(BaseModel):
    """登录请求"""
    username: str
    password: str


class TokenData(BaseModel):
    """Token 数据"""
    token: str
    refreshToken: str


class UserInfoData(BaseModel):
    """用户信息（Soybean Admin 兼容格式）"""
    userId: str
    userName: str
    roles: list[str]
    buttons: list[str]


# ===== 用户管理 CRUD =====

class UserResponse(BaseModel):
    """用户信息响应"""
    id: int
    username: str
    nickname: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    avatar: Optional[str] = None
    roles: list[str]
    status: str
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    """创建用户请求"""
    username: str
    password: str
    nickname: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    roles: list[str] = Field(default_factory=lambda: ["R_USER"])
    status: str = "active"


class UserUpdate(BaseModel):
    """更新用户请求（所有字段可选）"""
    username: Optional[str] = None
    password: Optional[str] = None
    nickname: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    roles: Optional[list[str]] = None
    status: Optional[str] = None


# ===== 分页 =====

class PageQuery(BaseModel):
    """分页查询参数"""
    current: int = 1
    size: int = 20
    username: Optional[str] = None
    status: Optional[str] = None


class PageResult(BaseModel):
    """分页结果"""
    records: list
    total: int
    current: int
    size: int
