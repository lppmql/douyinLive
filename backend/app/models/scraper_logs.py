"""采集日志表"""
from sqlalchemy import Column, BigInteger, String, Text, ForeignKey, JSON, Index
from app.models.base import Base, TimestampMixin


class ScraperLog(Base, TimestampMixin):
    """采集日志 — 包含原始数据备份"""

    __tablename__ = "scraper_logs"
    __table_args__ = (
        Index("idx_scraper_logs_task_id", "task_id", "id"),
        Index("idx_scraper_logs_level_id", "level", "id"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="日志ID")
    task_id = Column(BigInteger, ForeignKey("scraper_tasks.id"), nullable=True, comment="关联任务ID")
    level = Column(String(20), default="info", comment="级别: info/warn/error")
    message = Column(Text, nullable=True, comment="日志消息")
    raw_json = Column(JSON, nullable=True, comment="原始数据备份(JSON)")
