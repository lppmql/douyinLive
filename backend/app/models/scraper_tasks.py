"""采集任务表"""
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Text, ForeignKey, Index
from app.models.base import Base, TimestampMixin


class ScraperTask(Base, TimestampMixin):
    """采集任务 — 记录每次采集操作"""

    __tablename__ = "scraper_tasks"
    __table_args__ = (
        Index("idx_scraper_tasks_status_type", "status", "task_type", "id"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="任务ID")
    account_id = Column(Integer, ForeignKey("scraper_accounts.id"), nullable=True, comment="关联采集账号ID")
    session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=True, comment="关联直播场次ID")
    task_type = Column(String(50), nullable=False, comment="任务类型: login/metrics/comments/leads/profile")
    status = Column(String(20), default="pending", comment="状态: pending/running/completed/failed")
    started_at = Column(DateTime, nullable=True, comment="开始时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")
    error_message = Column(Text, nullable=True, comment="错误信息")
    progress_percent = Column(Integer, nullable=False, default=0, comment="任务进度百分比")
    progress_current = Column(Integer, nullable=False, default=0, comment="当前完成数量")
    progress_total = Column(Integer, nullable=False, default=0, comment="预计总数量")
    progress_stage = Column(String(50), nullable=True, comment="当前执行阶段")
    progress_message = Column(String(500), nullable=True, comment="当前进度说明")
    collected_anchor_count = Column(Integer, nullable=False, default=0, comment="本次已采集主播数")
    collected_session_count = Column(Integer, nullable=False, default=0, comment="本次已采集直播场次数")
    new_session_count = Column(Integer, nullable=False, default=0, comment="本次新增场次数")
    mapped_session_count = Column(Integer, nullable=False, default=0, comment="本次更新主播映射场次数")
    checked_detail_count = Column(Integer, nullable=False, default=0, comment="本次已检查详情场次数")
    refreshed_detail_count = Column(Integer, nullable=False, default=0, comment="本次已补齐详情场次数")
    failed_detail_count = Column(Integer, nullable=False, default=0, comment="本次详情采集失败场次数")
    remaining_detail_count = Column(Integer, nullable=False, default=0, comment="待补齐详情场次数")
