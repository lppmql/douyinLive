"""Phase 8: 认证 API — 登录 / 获取用户信息 / 刷新 Token"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.response import ok_response
from app.core.security import (
    verify_password,
    create_access_token,
    create_media_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    MEDIA_ACCESS_COOKIE,
)
from app.models.user import User
from pydantic import BaseModel
from app.schemas.auth import LoginRequest, SoybeanResponse, TokenData, UserInfoData


class SendCodeRequest(BaseModel):
    """发送验证码请求"""
    phone: str


class CodeLoginRequest(BaseModel):
    """验证码登录请求"""
    phone: str
    code: str
from app.services.sms import send_sms_code, verify_sms_code, TencentSmsError

router = APIRouter(prefix="/auth", tags=["认证"])


def _set_media_access_cookie(response: Response, user_id: int) -> None:
    """给浏览器原生图片和视频标签签发短时、只读、不可被 JS 读取的凭证。"""
    max_age = settings.MEDIA_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    response.set_cookie(
        key=MEDIA_ACCESS_COOKIE,
        value=create_media_access_token(user_id),
        max_age=max_age,
        expires=max_age,
        path="/",
        secure=not settings.DEBUG,
        httponly=True,
        samesite="lax",
    )


@router.post("/login", response_model=SoybeanResponse[TokenData])
def login(req: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """用户登录 → 返回 JWT Token"""
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用",
        )

    # 更新最后登录时间
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    token_data = {"sub": str(user.id)}
    _set_media_access_cookie(response, user.id)
    return ok_response(
        TokenData(
            token=create_access_token(token_data),
            refreshToken=create_refresh_token(token_data),
        ).model_dump()
    )


@router.post("/refreshToken", response_model=SoybeanResponse[TokenData])
def refresh_token(req: dict, response: Response, db: Session = Depends(get_db)):
    """刷新 Token"""
    refresh_token_str = req.get("refreshToken", "")
    payload = decode_token(refresh_token_str)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh Token 无效或已过期",
        )

    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh Token 载荷无效",
        )
    user = db.get(User, user_id)
    if user is None or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被禁用",
        )

    token_data = {"sub": str(user.id)}
    _set_media_access_cookie(response, user.id)
    return ok_response(
        TokenData(
            token=create_access_token(token_data),
            refreshToken=create_refresh_token(token_data),
        ).model_dump()
    )


@router.get("/getUserInfo", response_model=SoybeanResponse[UserInfoData])
def get_user_info(response: Response, current_user: User = Depends(get_current_user)):
    """获取当前登录用户信息（Soybean Admin 兼容格式）"""
    # 老登录会话刷新页面时也会经过此接口，因此无需用户退出重登即可补发媒体 Cookie。
    _set_media_access_cookie(response, current_user.id)
    return ok_response(
        UserInfoData(
            userId=str(current_user.id),
            userName=current_user.username,
            roles=current_user.roles or ["R_USER"],
            buttons=[],
        ).model_dump()
    )


@router.post("/send-code", response_model=SoybeanResponse)
def send_sms_code_endpoint(req: SendCodeRequest):
    """发送短信验证码"""
    try:
        import asyncio
        result = asyncio.run(send_sms_code(req.phone))
        return ok_response(result)
    except TencentSmsError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/code-login", response_model=SoybeanResponse[TokenData])
def code_login(req: CodeLoginRequest, response: Response, db: Session = Depends(get_db)):
    """手机号 + 验证码登录"""
    if not verify_sms_code(req.phone, req.code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="验证码错误或已过期",
        )

    from app.models.user import User
    user = db.query(User).filter(User.phone == req.phone).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="该手机号未注册，请先联系管理员创建账号",
        )
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用",
        )

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    token_data = {"sub": str(user.id)}
    _set_media_access_cookie(response, user.id)
    return ok_response(
        TokenData(
            token=create_access_token(token_data),
            refreshToken=create_refresh_token(token_data),
        ).model_dump()
    )
