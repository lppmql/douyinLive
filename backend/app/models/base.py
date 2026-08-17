"""SQLAlchemy 基础配置"""
from datetime import UTC, datetime
from sqlalchemy import Column, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def utc_now_naive() -> datetime:
    """返回与现有 MySQL DATETIME 契约兼容的无时区 UTC，避免 utcnow 弃用告警。"""
    return datetime.now(UTC).replace(tzinfo=None)


class TimestampMixin:
    """自动添加 created_at 和 updated_at 字段"""

    created_at = Column(DateTime, default=utc_now_naive, nullable=False, comment="创建时间")
    updated_at = Column(
        DateTime,
        default=utc_now_naive,
        onupdate=utc_now_naive,
        nullable=False,
        comment="更新时间",
    )
