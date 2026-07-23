"""采集日志表"""
from sqlalchemy import Column, BigInteger, Integer, String, Text, ForeignKey, JSON, Index
from app.models.base import Base, TimestampMixin


class ScraperLog(Base, TimestampMixin):
    """采集日志 — 包含原始数据备份"""

    __tablename__ = "scraper_logs"
    __table_args__ = (
        Index("idx_scraper_logs_task_id", "task_id", "id"),
        Index("idx_scraper_logs_level_id", "level", "id"),
        Index("idx_scraper_logs_session_id", "session_id", "id"),
        Index("idx_scraper_logs_stage_id", "stage", "id"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="日志ID")
    task_id = Column(BigInteger, ForeignKey("scraper_tasks.id"), nullable=True, comment="关联任务ID")
    level = Column(String(20), default="info", comment="级别: info/warn/error")
    message = Column(Text, nullable=True, comment="日志消息")
    raw_json = Column(JSON, nullable=True, comment="原始数据备份(JSON)")
    session_id = Column(Integer, nullable=True, comment="关联直播场次 ID 快照")
    anchor_name = Column(String(100), nullable=True, comment="关联主播名称快照")
    session_title = Column(String(255), nullable=True, comment="关联直播标题快照")
    room_id_str = Column(String(100), nullable=True, comment="平台直播房间 ID 快照")
    event_type = Column(String(50), nullable=True, comment="结构化日志事件类型")
    stage = Column(String(50), nullable=True, comment="任务执行阶段")
