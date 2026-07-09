"""留资数据表"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from app.models.base import Base, TimestampMixin


class Lead(Base, TimestampMixin):
    """留资数据 - 手机号脱敏显示"""

    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=False, comment="关联直播场次ID")
    lead_name = Column(String(100), nullable=True, comment="留资姓名")
    lead_phone = Column(String(20), nullable=True, comment="手机号")
    lead_source = Column(String(50), nullable=True, comment="来源：私信/小风车/表单/评论")
    is_valid = Column(Integer, default=1, comment="是否有效留资：1有效 0无效")
    remark = Column(String(500), nullable=True, comment="备注")
    create_time = Column(DateTime, nullable=True, comment="留资时间")
