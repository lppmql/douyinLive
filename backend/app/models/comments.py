"""评论/弹幕表"""
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Text, ForeignKey, Index
from app.models.base import Base, TimestampMixin


class Comment(Base, TimestampMixin):
    """评论/弹幕 - 含高意向标记、情绪"""

    __tablename__ = "comments"
    __table_args__ = (
        Index("idx_comments_session_time", "session_id", "comment_time", "id"),
        Index("idx_comments_intent_time", "is_high_intent", "comment_time"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="ID")
    session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=False, comment="关联直播场次ID")
    user_nickname = Column(String(100), nullable=True, comment="用户昵称")
    user_sec_uid = Column(String(200), nullable=True, comment="评论用户稳定SecUID")
    webcast_uid = Column(String(200), nullable=True, comment="本条评论Webcast用户标识")
    comment_content = Column(Text, nullable=True, comment="评论内容")
    comment_time = Column(DateTime, nullable=True, comment="评论时间")
    is_high_intent = Column(Integer, default=0, comment="是否高意向：1是 0否")
    sentiment = Column(String(20), nullable=True, comment="情绪倾向：positive/neutral/negative")
    keywords = Column(String(500), nullable=True, comment="关键词（逗号分隔）")
