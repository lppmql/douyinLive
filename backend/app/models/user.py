"""系统用户表"""
from sqlalchemy import Column, Integer, String, DateTime, JSON
from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """系统用户"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="用户ID")
    username = Column(String(64), unique=True, nullable=False, comment="用户名")
    password_hash = Column(String(256), nullable=False, comment="密码哈希（bcrypt）")
    nickname = Column(String(64), default="", comment="昵称")
    email = Column(String(128), default="", comment="邮箱")
    phone = Column(String(20), default="", comment="手机号")
    avatar = Column(String(256), default="", comment="头像 URL")
    roles = Column(JSON, default=lambda: ["R_USER"], comment="角色列表")
    status = Column(String(20), default="active", comment="状态: active / disabled")
    last_login_at = Column(DateTime, nullable=True, comment="最后登录时间")
