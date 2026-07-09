"""简易认证 API — 用于前端 Soybean Admin 登录"""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["认证"])


class LoginRequest(BaseModel):
    userName: str
    password: str


class LoginResponse(BaseModel):
    token: str
    refreshToken: str


class UserInfoResponse(BaseModel):
    userId: str
    userName: str
    roles: list[str]
    buttons: list[str]


@router.post("/login", response_model=LoginResponse)
def login(data: LoginRequest):
    """登录 — 返回固定 token（开发环境）"""
    return LoginResponse(
        token="dev-token-douyin-live",
        refreshToken="dev-refresh-token",
    )


@router.get("/getUserInfo", response_model=UserInfoResponse)
def get_user_info():
    """获取用户信息 — 返回超级管理员角色"""
    return UserInfoResponse(
        userId="1",
        userName="开发者",
        roles=["R_SUPER"],
        buttons=["*"],
    )
