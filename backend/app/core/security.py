"""JWT Token 签发/验证 + 密码哈希 + 当前用户依赖。"""
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User

MEDIA_ACCESS_COOKIE = "douyin_media_access"
_MEDIA_PATH_PATTERN = re.compile(
    r"^/api/v1/live-sessions/\d+/(?:avatar|video|playback|comments/\d+/avatar)$"
)

# auto_error=False 让依赖有机会读取只用于原生媒体标签的 HttpOnly Cookie。
security = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码 vs bcrypt 哈希"""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except (TypeError, ValueError):
        return False


def get_password_hash(password: str) -> str:
    """生成 bcrypt 密码哈希"""
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 72:
        raise ValueError("密码的 UTF-8 编码不能超过 72 字节")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建 JWT access token"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """创建 JWT refresh token（有效期 7 天）"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_media_access_token(user_id: int) -> str:
    """创建仅允许读取头像、回放和下载地址的短时 Token。"""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.MEDIA_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire, "type": "media"}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """解码并验证 JWT token，失败返回 None"""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """解析当前用户；短时媒体 Cookie 只能用于明确的只读媒体路径。"""
    expected_type = "access"
    token = credentials.credentials if credentials else None
    if token is None and request.method == "GET" and _MEDIA_PATH_PATTERN.fullmatch(request.url.path):
        token = request.cookies.get(MEDIA_ACCESS_COOKIE)
        expected_type = "media"

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
        )

    payload = decode_token(token)
    if payload is None or payload.get("type") != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
        )
    user_id = payload.get("sub")
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 载荷无效",
        )
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用",
        )
    return user
