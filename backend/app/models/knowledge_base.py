"""知识库表"""
from sqlalchemy import Column, Integer, String, Text, ForeignKey
from app.models.base import Base, TimestampMixin


class KnowledgeBase(Base, TimestampMixin):
    """知识库 - 含分类、标签、来源、预留给向量检索的 embedding_json"""

    __tablename__ = "knowledge_base"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=True, comment="关联直播场次ID")
    category = Column(String(50), nullable=True, comment="分类：优质话术/分析结论/优化案例")
    title = Column(String(200), nullable=True, comment="标题")
    content = Column(Text, nullable=True, comment="内容")
    source_type = Column(String(30), nullable=True, comment="来源：ai_analysis/manual/transcript")
    embedding_json = Column(Text, nullable=True, comment="预留给向量检索的 embedding 数据")
