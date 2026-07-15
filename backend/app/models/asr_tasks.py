"""ASR 转写任务表 — 并发控制与管理"""
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Text, ForeignKey, Index
from app.models.base import Base, TimestampMixin


class AsrTask(Base, TimestampMixin):
    """ASR 转写任务"""

    __tablename__ = "asr_tasks"
    __table_args__ = (
        Index("idx_asr_tasks_status_created", "status", "created_at"),
        Index("idx_asr_tasks_idempotency", "idempotency_key", unique=True),
        Index("idx_asr_tasks_trace", "trace_id"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="任务ID")
    session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=False, comment="关联直播场次")
    stream_id = Column(Integer, ForeignKey("stream_sources.id"), nullable=True, comment="关联流源")
    status = Column(String(20), default="queued", comment="状态: queued/processing/completed/failed")
    task_type = Column(String(20), default="realtime", comment="任务类型: realtime/offline")
    started_at = Column(DateTime, nullable=True, comment="开始时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")
    error_message = Column(Text, nullable=True, comment="错误信息")
    idempotency_key = Column(String(100), nullable=True, comment="幂等键，防止重复转写")
    trace_id = Column(String(64), nullable=True, comment="任务链路追踪ID")
    worker_id = Column(String(100), nullable=True, comment="当前执行Worker")
    heartbeat_at = Column(DateTime, nullable=True, comment="最近心跳时间")
    retry_count = Column(Integer, nullable=False, default=0, comment="已执行次数")
    max_retries = Column(Integer, nullable=False, default=3, comment="最大执行次数")
    priority = Column(Integer, nullable=False, default=50, comment="优先级，数值越小越优先")
