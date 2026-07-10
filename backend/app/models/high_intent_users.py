"""高意向用户表 - AI 从评论中识别"""
from sqlalchemy import Column, Integer, BigInteger, String, Text, DateTime, ForeignKey
from app.models.base import Base, TimestampMixin


class HighIntentUser(Base, TimestampMixin):
    """高意向用户 - AI 从评论中识别出的有购买意向的用户"""

    __tablename__ = "high_intent_users"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=False, comment="关联直播场次ID")
    comment_id = Column(BigInteger, ForeignKey("comments.id"), nullable=True, comment="关联评论ID")
    user_name = Column(String(100), nullable=True, comment="用户昵称")
    phone = Column(String(20), nullable=True, comment="手机号（脱敏）")
    product_interest = Column(String(200), nullable=True, comment="感兴趣的产品/服务")
    intent_level = Column(String(20), default="medium", comment="意向等级：high/medium/low")
    intent_reason = Column(Text, nullable=True, comment="AI判断依据")
    is_contacted = Column(Integer, default=0, comment="是否已联系：1是 0否")
    contacted_at = Column(DateTime, nullable=True, comment="联系时间")
    contact_note = Column(Text, nullable=True, comment="联系备注")
