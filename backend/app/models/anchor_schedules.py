"""主播每日排班模板。"""
from sqlalchemy import Boolean, Column, Integer, JSON, String, Time, UniqueConstraint

from app.models.base import Base, TimestampMixin


class AnchorSchedule(Base, TimestampMixin):
    """从排班表导入的每日固定班次。"""

    __tablename__ = "anchor_schedules"
    __table_args__ = (
        UniqueConstraint("source_anchor_name", "session_index", name="uq_anchor_schedule_slot"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="排班ID")
    source_anchor_name = Column(String(100), nullable=False, comment="排班表中的主播姓名")
    display_name = Column(String(100), nullable=False, comment="页面展示名称")
    match_keywords = Column(JSON, nullable=False, comment="匹配真实采集主播名称的关键词")
    room_name = Column(String(100), nullable=False, comment="直播间")
    network_name = Column(String(100), nullable=True, comment="直播网络")
    session_index = Column(Integer, nullable=False, comment="主播当天第几场")
    planned_start_time = Column(Time, nullable=False, comment="计划开播时间")
    planned_end_time = Column(Time, nullable=False, comment="计划下播时间")
    expected_duration_minutes = Column(Integer, nullable=False, default=80, comment="标准直播分钟数")
    active = Column(Boolean, nullable=False, default=True, comment="是否启用")
    source_name = Column(String(200), nullable=False, default="排班.xls", comment="排班来源")
