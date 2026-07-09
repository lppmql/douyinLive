"""评论/弹幕表"""
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Text, ForeignKey
from app.models.base import Base, TimestampMixin


class Comment(Base, TimestampMixin):
    """评论/弹幕 - 含高意向标记、情绪"""

    __tablename__ = "comments"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="ID")
    session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=False, comment="关联直播场次ID")
    user_nickname = Column(String(100), nullable=True, comment="用户昵称")
    comment_content = Column(Text, nullable=True, comment="评论内容")
    comment_time = Column(DateTime, nullable=True, comment="评论时间")
    is_high_intent = Column(Integer, default=0, comment="是否高意向：1是 0否")
    sentiment = Column(String(20), nullable=True, comment="情绪倾向：positive/neutral/negative")
    keywords = Column(String(500), nullable=True, comment="关键词（逗号分隔）")
