"""ASR 转写任务表 — 并发控制与管理"""
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Text, ForeignKey, Index
from app.models.base import Base, TimestampMixin


class AsrTask(Base, TimestampMixin):
    """ASR 转写任务"""

    __tablename__ = "asr_tasks"
    __table_args__ = (
        Index("idx_asr_tasks_status_created", "status", "created_at"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="任务ID")
    session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=False, comment="关联直播场次")
    stream_id = Column(Integer, ForeignKey("stream_sources.id"), nullable=True, comment="关联流源")
    status = Column(String(20), default="queued", comment="状态: queued/processing/completed/failed")
    task_type = Column(String(20), default="realtime", comment="任务类型: realtime/offline")
    started_at = Column(DateTime, nullable=True, comment="开始时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")
    error_message = Column(Text, nullable=True, comment="错误信息")
