"""Phase 8: 认证 API — 登录 / 获取用户信息 / 刷新 Token"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ok_response
from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
)
from app.models.user import User
from app.schemas.auth import LoginRequest, SoybeanResponse, TokenData, UserInfoData

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", response_model=SoybeanResponse[TokenData])
def login(req: LoginRequest, db: Session = Depends(get_db)):
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
    return ok_response(
        TokenData(
            token=create_access_token(token_data),
            refreshToken=create_refresh_token(token_data),
        ).model_dump()
    )


@router.post("/refreshToken", response_model=SoybeanResponse[TokenData])
def refresh_token(req: dict, db: Session = Depends(get_db)):
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
    return ok_response(
        TokenData(
            token=create_access_token(token_data),
            refreshToken=create_refresh_token(token_data),
        ).model_dump()
    )


@router.get("/getUserInfo", response_model=SoybeanResponse[UserInfoData])
def get_user_info(current_user: User = Depends(get_current_user)):
    """获取当前登录用户信息（Soybean Admin 兼容格式）"""
    return ok_response(
        UserInfoData(
            userId=str(current_user.id),
            userName=current_user.username,
            roles=current_user.roles or ["R_USER"],
            buttons=[],
        ).model_dump()
    )
