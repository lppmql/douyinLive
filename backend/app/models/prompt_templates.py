"""提示词模板表"""
from sqlalchemy import Column, Integer, String, Text
from app.models.base import Base, TimestampMixin


class PromptTemplate(Base, TimestampMixin):
    """AI 提示词模板 — 不写死在 Python 代码里"""

    __tablename__ = "prompt_templates"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    type = Column(String(50), nullable=False, index=True, comment="类型：speech_score/trend_analysis/anomaly/optimization/qa")
    name = Column(String(100), nullable=True, comment="模板名称")
    content = Column(Text, nullable=False, comment="提示词内容（含变量占位符）")
    version = Column(Integer, nullable=False, default=1, comment="版本号")
    description = Column(String(500), nullable=True, comment="用途说明")
