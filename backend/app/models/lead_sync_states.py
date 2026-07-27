"""外部客资增量同步游标。"""

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text

from app.models.base import Base, TimestampMixin


class LeadSyncState(Base, TimestampMixin):
    """记录“上次拉到哪里”，服务重启后也能继续而不是从头重复读取。"""

    __tablename__ = "lead_sync_states"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    source_system = Column(String(50), nullable=False, unique=True, comment="外部客资系统标识")
    last_external_id = Column(BigInteger, nullable=False, default=0, comment="已成功保存的最大外部编号")
    status = Column(String(20), nullable=False, default="idle", comment="idle/running/completed/failed")
    last_synced_at = Column(DateTime, nullable=True, comment="最近成功同步时间")
    last_error = Column(Text, nullable=True, comment="最近一次失败原因，不包含客资隐私")
    synced_count = Column(Integer, nullable=False, default=0, comment="累计新增客资数")
    duplicate_count = Column(Integer, nullable=False, default=0, comment="累计跳过重复数")
    pending_count = Column(Integer, nullable=False, default=0, comment="待人工归属场次数")
