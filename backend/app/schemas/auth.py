"""认证相关 Pydantic 模型 — 登录 / 用户信息 / 用户管理"""
from datetime import datetime
from typing import Generic, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, Field, field_validator

# 泛型类型变量，用于 SoybeanResponse 包装
T = TypeVar("T")


# ===== SoybeanAdmin 通用响应包装 =====

class SoybeanResponse(BaseModel, Generic[T]):
    """SoybeanAdmin 前端兼容的成功响应格式

    所有 API 返回 `{"code": "0000", "data": ..., "msg": "success"}` 格式。
    通过泛型 T 指定 data 字段类型，让 Swagger 自动生成准确的文档。

    使用示例：
        @router.post("/login", response_model=SoybeanResponse[TokenData])
        def login(...):
            return ok_response(data=TokenData(...).model_dump())
    """
    code: str = "0000"
    data: Optional[T] = None
    msg: str = "success"


# ===== 登录认证 =====

class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(min_length=1, max_length=100, description="用户名，不能为空")
    password: str = Field(min_length=1, max_length=128, description="密码，不能为空")


class SendCodeRequest(BaseModel):
    """发送短信验证码请求。"""

    phone: str = Field(pattern=r"^1[3-9]\d{9}$", description="中国大陆 11 位手机号")


class CodeLoginRequest(BaseModel):
    """手机号验证码登录请求。"""

    phone: str = Field(pattern=r"^1[3-9]\d{9}$", description="中国大陆 11 位手机号")
    code: str = Field(pattern=r"^\d{6}$", description="6 位数字验证码")


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
    model_config = ConfigDict(from_attributes=True)

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

class UserCreate(BaseModel):
    """创建用户请求"""
    username: str = Field(min_length=1, max_length=100, description="用户名")
    password: str = Field(min_length=6, max_length=128, description="密码，最少 6 位")
    nickname: Optional[str] = Field(default=None, max_length=100, description="昵称")
    email: Optional[str] = Field(default=None, max_length=200, description="邮箱")
    phone: Optional[str] = Field(default=None, max_length=30, description="手机号")
    roles: list[str] = Field(default_factory=lambda: ["R_USER"])
    status: str = Field(default="active", pattern="^(active|disabled)$", description="用户状态")

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, value: list[str]) -> list[str]:
        """只接受系统定义的三种角色，未知角色默认不能入库。"""
        allowed = {"R_VIEWER", "R_USER", "R_SUPER"}
        if not value or any(role not in allowed for role in value):
            raise ValueError("角色只能是 R_VIEWER、R_USER 或 R_SUPER")
        return sorted(set(value))


class UserUpdate(BaseModel):
    """更新用户请求（所有字段可选）"""
    username: Optional[str] = None
    password: Optional[str] = None
    nickname: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    roles: Optional[list[str]] = None
    status: Optional[str] = None

    @field_validator("roles")
    @classmethod
    def validate_optional_roles(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        if value is None:
            return None
        return UserCreate.validate_roles(value)


# ===== 分页 =====

class PageQuery(BaseModel):
    """分页查询参数"""
    current: int = 1
    size: int = 20
    username: Optional[str] = None
    status: Optional[str] = None


class PageResult(BaseModel, Generic[T]):
    """分页结果"""
    records: list[T]
    total: int
    current: int
    size: int
