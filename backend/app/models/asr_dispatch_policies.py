"""ASR 调度策略表。"""

from sqlalchemy import Column, Integer, String

from app.models.base import Base, TimestampMixin


class AsrDispatchPolicy(Base, TimestampMixin):
    """单例调度策略，保存主播话术页选择的自动队列排序。"""

    __tablename__ = "asr_dispatch_policies"

    id = Column(
        Integer, primary_key=True, autoincrement=False, default=1, comment="固定单例ID"
    )
    order_mode = Column(
        String(20),
        nullable=False,
        default="smart",
        comment="自动队列排序: smart/latest/fifo",
    )
