"""完整话术拼接表"""
from sqlalchemy import Column, Integer, Text, ForeignKey
from app.models.base import Base, TimestampMixin


class TranscriptFullText(Base, TimestampMixin):
    """完整拼接文本 - 每场直播一条完整话术"""

    __tablename__ = "transcript_full_texts"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=False, comment="关联直播场次ID")
    full_text = Column(Text, nullable=True, comment="完整拼接话术")
