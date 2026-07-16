"""完整话术拼接表"""
from sqlalchemy import Column, ForeignKey, Integer
from sqlalchemy.dialects.mysql import LONGTEXT

from app.models.base import Base, TimestampMixin


class TranscriptFullText(Base, TimestampMixin):
    """完整拼接文本 - 每场直播一条完整话术"""

    __tablename__ = "transcript_full_texts"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=False, comment="关联直播场次ID")
    full_text = Column(LONGTEXT, nullable=True, comment="完整拼接话术")
