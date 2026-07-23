"""数据采集六个长期运行模块的持久开关状态。"""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Index, Integer, String

from app.models.base import Base, TimestampMixin


class CollectorModuleState(Base, TimestampMixin):
    """保存模块是否长期运行，以及下一次增量检查时间。"""

    __tablename__ = "collector_module_states"
    __table_args__ = (
        Index("idx_collector_module_enabled_next", "enabled", "next_run_at"),
    )

    module_key = Column(String(32), primary_key=True, comment="模块唯一标识")
    enabled = Column(Boolean, nullable=False, default=False, comment="是否长期运行")
    interval_seconds = Column(Integer, nullable=False, default=60, comment="增量检查间隔秒数")
    enabled_at = Column(DateTime, nullable=True, comment="最近开启时间")
    disabled_at = Column(DateTime, nullable=True, comment="最近彻底关闭时间")
    last_scheduled_at = Column(DateTime, nullable=True, comment="最近创建增量任务时间")
    next_run_at = Column(DateTime, nullable=True, comment="下一次增量检查时间")
    last_task_id = Column(BigInteger, nullable=True, comment="最近一次关联任务 ID")
    last_error = Column(String(500), nullable=True, comment="最近一次调度错误或资源保护原因")
