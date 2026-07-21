"""Phase 8: 用户管理 CRUD API（仅管理员可用）"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ok_response
from app.core.security import get_password_hash, get_current_user
from app.models.user import User
from app.schemas.auth import PageResult, SoybeanResponse, UserResponse, UserCreate, UserUpdate

router = APIRouter(prefix="/users", tags=["用户管理"])


def _require_admin(current_user: User = Depends(get_current_user)):
    """检查当前用户是否为超级管理员"""
    roles = current_user.roles or []
    if "R_SUPER" not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return current_user


@router.get("/", response_model=SoybeanResponse[PageResult[UserResponse]])
def list_users(
    current: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页条数"),
    username: Optional[str] = Query(None, description="用户名关键词搜索"),
    status: Optional[str] = Query(None, description="状态过滤"),
    db: Session = Depends(get_db),
    _admin: User = Depends(_require_admin),
):
    """获取用户列表（分页）"""
    q = db.query(User)
    if username:
        q = q.filter(User.username.like(f"%{username}%"))
    if status:
        q = q.filter(User.status == status)
    total = q.count()
    users = (
        q.order_by(User.id.asc())
        .offset((current - 1) * size)
        .limit(size)
        .all()
    )
    return ok_response({
        "records": [UserResponse.model_validate(u).model_dump() for u in users],
        "total": total,
        "current": current,
        "size": size,
    })


@router.get("/{user_id}", response_model=SoybeanResponse[UserResponse])
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(_require_admin),
):
    """获取单个用户详情"""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return ok_response(UserResponse.model_validate(user).model_dump())


@router.post("/", status_code=201, response_model=SoybeanResponse[UserResponse])
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(_require_admin),
):
    """新建用户"""
    existing = db.query(User).filter(User.username == data.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = User(
        username=data.username,
        password_hash=get_password_hash(data.password),
        nickname=data.nickname or data.username,
        email=data.email or "",
        phone=data.phone or "",
        roles=data.roles or ["R_USER"],
        status=data.status or "active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return ok_response(UserResponse.model_validate(user).model_dump(), msg="创建成功")


@router.put("/{user_id}", response_model=SoybeanResponse[UserResponse])
def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(_require_admin),
):
    """编辑用户"""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    update_dict = data.model_dump(exclude_unset=True, exclude={"password"})
    if data.password:
        update_dict["password_hash"] = get_password_hash(data.password)

    for key, value in update_dict.items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return ok_response(UserResponse.model_validate(user).model_dump(), msg="更新成功")


@router.delete("/{user_id}", response_model=SoybeanResponse[None])
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(_require_admin),
):
    """删除用户"""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="不能删除当前登录账号")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    db.delete(user)
    db.commit()
    return ok_response(None, msg="删除成功")
