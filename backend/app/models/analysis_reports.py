"""AI 分析报告表"""
from sqlalchemy import Column, Integer, String, Text, JSON, ForeignKey
from app.models.base import Base, TimestampMixin


class AnalysisReport(Base, TimestampMixin):
    """AI 分析报告 - JSON格式存储报告内容"""

    __tablename__ = "analysis_reports"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=False, comment="关联直播场次ID")
    report_type = Column(String(30), nullable=False, comment="类型：speech_score/trend/anomaly/optimization")
    report_title = Column(String(200), nullable=True, comment="报告标题")
    report_content = Column(JSON, nullable=True, comment="报告内容（JSON格式）")
    summary = Column(Text, nullable=True, comment="摘要")
