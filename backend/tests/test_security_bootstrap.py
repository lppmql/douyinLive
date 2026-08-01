"""全新安装管理员的安全启动测试。"""

import pytest

from app.core.config import settings
from app.models.user import User
from app.services.security.bootstrap import bootstrap_admin_if_empty


def test_empty_database_without_strong_bootstrap_password_stops_startup(db, monkeypatch):
    """空用户表不能静默启动，否则系统会变成没有任何人能登录。"""
    monkeypatch.setattr(settings, "BOOTSTRAP_ADMIN_USERNAME", "")
    monkeypatch.setattr(settings, "BOOTSTRAP_ADMIN_PASSWORD", "")
    monkeypatch.setattr(settings, "DEBUG", False)

    with pytest.raises(RuntimeError, match="全新安装必须"):
        bootstrap_admin_if_empty(db)


def test_empty_database_creates_super_admin_from_environment(db, monkeypatch):
    """合格环境变量只在空库创建一次真实管理员，不使用公开默认密码。"""
    monkeypatch.setattr(settings, "BOOTSTRAP_ADMIN_USERNAME", "secure-admin")
    monkeypatch.setattr(settings, "BOOTSTRAP_ADMIN_PASSWORD", "a-strong-password-2026")
    monkeypatch.setattr(settings, "DEBUG", False)

    assert bootstrap_admin_if_empty(db) is True
    created = db.query(User).filter(User.username == "secure-admin").one()
    assert created.roles == ["R_SUPER"]
    assert created.password_hash != "a-strong-password-2026"
    assert bootstrap_admin_if_empty(db) is False


def test_local_debug_allows_documented_first_run_admin_password(db, monkeypatch):
    monkeypatch.setattr(settings, "BOOTSTRAP_ADMIN_USERNAME", "admin")
    monkeypatch.setattr(settings, "BOOTSTRAP_ADMIN_PASSWORD", "admin123")
    monkeypatch.setattr(settings, "DEBUG", True)

    assert bootstrap_admin_if_empty(db) is True
    assert db.query(User).filter(User.username == "admin").one().roles == ["R_SUPER"]


def test_production_allows_documented_first_run_admin_password(db, monkeypatch):
    monkeypatch.setattr(settings, "BOOTSTRAP_ADMIN_USERNAME", "admin")
    monkeypatch.setattr(settings, "BOOTSTRAP_ADMIN_PASSWORD", "admin123")
    monkeypatch.setattr(settings, "DEBUG", False)

    assert bootstrap_admin_if_empty(db) is True
    assert db.query(User).filter(User.username == "admin").one().roles == ["R_SUPER"]
