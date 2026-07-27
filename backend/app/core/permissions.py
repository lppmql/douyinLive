"""业务角色权限。

角色用大白话解释：
- R_VIEWER：只看数据，不能改动。
- R_USER：日常运营，可以采集、转写和编辑业务数据。
- R_SUPER：超级管理员，可以删除数据和管理用户。

所有业务请求都先经过这里，默认拒绝未知角色，避免只在前端隐藏按钮造成越权。
"""

from fastapi import Depends, HTTPException, Request, status

from app.core.security import get_current_user
from app.models.user import User

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_KNOWN_ROLES = {"R_VIEWER", "R_USER", "R_SUPER"}


def normalize_roles(roles: list[str] | None) -> set[str]:
    """统一旧角色名称，保证升级后老账号不会突然无法工作。"""
    normalized = set(roles or [])
    # 早期测试和少量旧账号使用 R_ADMIN；升级后按超级管理员兼容。
    if "R_ADMIN" in normalized:
        normalized.add("R_SUPER")
    return normalized & _KNOWN_ROLES


def is_business_action_allowed(roles: list[str] | None, method: str, path: str) -> bool:
    """判断某个角色能否执行请求；没有明确允许时一律拒绝。"""
    normalized = normalize_roles(roles)
    if not normalized:
        return False
    if "R_SUPER" in normalized:
        return True

    # 用户管理包含账号、手机号和权限，只允许超级管理员访问。
    if path.startswith("/api/v1/users"):
        return False

    method = method.upper()
    if method in _SAFE_METHODS:
        return bool(normalized & {"R_VIEWER", "R_USER"})

    # 删除通常不可恢复，统一收紧到超级管理员。
    if method == "DELETE":
        return False

    # 日常运营账号可以创建、修改和触发业务任务。
    return "R_USER" in normalized and method in {"POST", "PUT", "PATCH"}


def enforce_business_permissions(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> User:
    """FastAPI 依赖：每个业务请求都执行后端权限校验。"""
    if not is_business_action_allowed(current_user.roles, request.method, request.url.path):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前账号没有执行此操作的权限",
        )
    return current_user
