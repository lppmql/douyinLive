"""SQLAlchemy 基础配置"""
from datetime import datetime
from sqlalchemy import Column, DateTime, func
from sqlalchemy.orm import declarative_base, declared_attr

Base = declarative_base()


class TimestampMixin:
    """自动添加 created_at 和 updated_at 字段"""

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        comment="更新时间",
    )
