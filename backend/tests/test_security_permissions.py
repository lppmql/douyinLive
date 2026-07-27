"""A1 安全基础：角色权限和内部 Worker 凭证测试。"""

from app.core.security import create_access_token
from app.core.permissions import is_business_action_allowed, normalize_roles
from app.core.security import build_internal_worker_token, verify_internal_worker_token
from app.models.user import User


def test_viewer_is_strictly_read_only():
    """只读账号可以看数据，但不能创建、修改或删除业务数据。"""
    roles = ["R_VIEWER"]

    assert is_business_action_allowed(roles, "GET", "/api/v1/dashboard/summary") is True
    assert is_business_action_allowed(roles, "POST", "/api/v1/transcripts/1/queue") is False
    assert is_business_action_allowed(roles, "DELETE", "/api/v1/transcripts/tasks/1") is False


def test_operator_can_operate_but_cannot_delete_or_manage_users():
    """运营账号负责日常业务操作，高风险删除和用户管理仍只允许超级管理员。"""
    roles = ["R_USER"]

    assert is_business_action_allowed(roles, "POST", "/api/v1/transcripts/1/queue") is True
    assert is_business_action_allowed(roles, "DELETE", "/api/v1/live-sessions/1") is False
    assert is_business_action_allowed(roles, "GET", "/api/v1/users/") is False


def test_super_admin_can_execute_high_risk_actions():
    """超级管理员拥有完整管理权限。"""
    roles = ["R_SUPER"]

    assert is_business_action_allowed(roles, "DELETE", "/api/v1/live-sessions/1") is True
    assert is_business_action_allowed(roles, "GET", "/api/v1/users/") is True


def test_legacy_admin_is_normalized_to_super_admin():
    """升级前的 R_ADMIN 账号必须继续拥有管理员能力，但新逻辑只使用 R_SUPER。"""
    assert normalize_roles(["R_ADMIN"]) == {"R_SUPER"}
    assert is_business_action_allowed(["R_ADMIN"], "GET", "/api/v1/users/") is True


def test_unknown_role_is_denied_by_default():
    """未知角色默认拒绝，避免拼错角色后意外获得权限。"""
    assert is_business_action_allowed(["R_UNKNOWN"], "GET", "/api/v1/dashboard/summary") is False


def test_internal_worker_token_is_separate_from_browser_access_token():
    """ASR Worker 使用专用派生凭证，浏览器 JWT 不能冒充内部服务。"""
    token = build_internal_worker_token()

    assert verify_internal_worker_token(token) is True
    assert verify_internal_worker_token("not-a-worker-token") is False


def test_viewer_business_write_is_rejected_by_api(client, db):
    """前端即使手工构造 POST 请求，后端也必须拒绝只读账号。"""
    viewer = User(
        username="readonly",
        password_hash="not-used-in-this-test",
        nickname="只读验收账号",
        roles=["R_VIEWER"],
        status="active",
    )
    db.add(viewer)
    db.commit()
    db.refresh(viewer)
    token = create_access_token({"sub": str(viewer.id)})

    response = client.post(
        "/api/v1/transcripts/1/queue",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "当前账号没有执行此操作的权限"


def test_legacy_admin_can_access_user_management(client, auth_headers):
    """旧管理员登录后仍能进入用户管理，避免升级后突然失权。"""
    response = client.get("/api/v1/users/", headers=auth_headers)

    assert response.status_code == 200
