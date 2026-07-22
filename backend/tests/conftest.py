"""
M8: 集成测试基础设施
====================
使用 SQLite 内存数据库 + FastAPI TestClient 实现 auth → collector → dashboard
核心链路端到端测试。

关键设计：
- SQLite 内存数据库（零外部依赖，无需 MySQL/Redis）
- StaticPool 确保同一连接复用（内存数据库不丢失）
- 独立 FastAPI app（无 lifespan，避免 Redis/ASR/scheduler 副作用）
- 每个测试函数独立建表/删表（保证隔离性）

环境变量警告：
本文件必须在导入任何 app.* 模块前设置 DATABASE_URL=sqlite:///:memory:，
否则 app.core.database 会在模块级别创建指向 MySQL 的 engine。
"""

import os

# ⚠️ 关键：必须在任何 app.* 导入之前设置
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, Text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# 模型使用 app.models.base.Base（与 app.core.database.Base 不是同一个 declarative_base！）
from app.models.base import Base
from app.core.database import get_db
from app.api.v1 import v1_router
from app.api.v1.auth import router as auth_router
from app.core.security import get_password_hash

# 确保所有模型已注册到 Base.metadata（create_all 需要）
import app.models  # noqa: F401 — 触发 models/__init__.py 中的全部模型导入


def _patch_longtext_for_sqlite() -> dict:
    """
    SQLite 不支持 MySQL 方言的 LONGTEXT 类型，在 create_all 前
    将 LONGTEXT 列替换为标准 TEXT，返回原始类型映射用于后续恢复。

    注意：Base.metadata.tables 是全局共享对象，修改列类型会影响到
    其他不使用 client fixture 的测试（如 test_task_reliability.py），
    因此必须在使用后恢复原始类型。
    """
    original_types: dict[tuple[str, str], object] = {}
    for table_name, table in Base.metadata.tables.items():
        for column in table.columns:
            type_name = str(column.type).upper()
            if "LONGTEXT" in type_name:
                original_types[(table_name, column.name)] = column.type
                column.type = Text()
    return original_types


def _restore_longtext(original_types: dict) -> None:
    """恢复 _patch_longtext_for_sqlite 修改的列类型为原始 MySQL 类型。"""
    for (table_name, column_name), original_type in original_types.items():
        table = Base.metadata.tables.get(table_name)
        if table is not None:
            column = table.columns.get(column_name)
            if column is not None:
                column.type = original_type

# ============================================================
#  测试数据库引擎（SQLite 内存，StaticPool 确保连接复用）
# ============================================================
TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


def override_get_db():
    """FastAPI 依赖覆写：用 SQLite 测试会话替代 MySQL 会话。"""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================
#  测试 FastAPI app
#  不继承 main.py 的 lifespan（避免 Redis/ASR/scheduler/浏览器池启动）
# ============================================================
test_app = FastAPI(title="Test App - 集成测试")
# auth_router 单独注册（含公开的 login/refreshToken，不经过 v1_router 的全局鉴权）
test_app.include_router(auth_router, prefix="/api/v1")
test_app.include_router(v1_router)
test_app.dependency_overrides[get_db] = override_get_db


# ============================================================
#  Pytest Fixtures
# ============================================================


@pytest.fixture(scope="function")
def client():
    """每个测试函数独立的 TestClient，自动创建/销毁数据库表。"""
    original_types = _patch_longtext_for_sqlite()
    Base.metadata.create_all(bind=TEST_ENGINE)
    with TestClient(test_app) as c:
        yield c
    Base.metadata.drop_all(bind=TEST_ENGINE)
    _restore_longtext(original_types)


@pytest.fixture(scope="function")
def db(client):
    """
    数据库会话，用于在测试前插入种子数据。

    注意：此 session 与 TestClient 内部使用的 session 共享同一个
    SQLite 连接（StaticPool），所以种子数据对 API 端点可见。
    """
    db_session = TestSessionLocal()
    try:
        yield db_session
    finally:
        db_session.rollback()
        db_session.close()


@pytest.fixture(scope="function")
def test_user(db):
    """
    创建测试用户，返回 (User对象, 明文密码)。
    密码: test123456，角色: R_ADMIN，状态: active。
    """
    from app.models.user import User

    password = "test123456"
    user = User(
        username="testuser",
        password_hash=get_password_hash(password),
        nickname="测试用户",
        roles=["R_ADMIN"],
        status="active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, password


@pytest.fixture(scope="function")
def auth_headers(client, test_user):
    """
    返回带 Bearer token 的认证请求头。
    用 test_user 的凭据先执行登录，从响应中提取 token。
    """
    user, password = test_user
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": password},
    )
    assert resp.status_code == 200, f"登录失败: {resp.json()}"
    token = resp.json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}
