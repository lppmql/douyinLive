"""采集任务表"""
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Text, ForeignKey
from app.models.base import Base, TimestampMixin


class ScraperTask(Base, TimestampMixin):
    """采集任务 — 记录每次采集操作"""

    __tablename__ = "scraper_tasks"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="任务ID")
    account_id = Column(Integer, ForeignKey("scraper_accounts.id"), nullable=True, comment="关联采集账号ID")
    session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=True, comment="关联直播场次ID")
    task_type = Column(String(50), nullable=False, comment="任务类型: login/metrics/comments/leads/profile")
    status = Column(String(20), default="pending", comment="状态: pending/running/completed/failed")
    started_at = Column(DateTime, nullable=True, comment="开始时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")
    error_message = Column(Text, nullable=True, comment="错误信息")
