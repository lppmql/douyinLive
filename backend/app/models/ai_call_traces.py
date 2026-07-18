"""轻量 AI 调用追踪表。"""
from sqlalchemy import BigInteger, Column, ForeignKey, Index, Integer, String

from app.models.base import Base, TimestampMixin


class AiCallTrace(Base, TimestampMixin):
    """只保存调用元数据，不复制真实话术、评论、Prompt 或模型输出。"""

    __tablename__ = "ai_call_traces"
    __table_args__ = (
        Index("idx_ai_call_trace_trace", "trace_id"),
        Index("idx_ai_call_trace_session_created", "session_id", "created_at"),
        Index("idx_ai_call_trace_operation_status", "operation", "status", "created_at"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="AI调用ID")
    trace_id = Column(String(128), nullable=False, comment="应用链路追踪ID")
    session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=True, comment="关联真实直播场次")
    operation = Column(String(50), nullable=False, comment="业务操作类型")
    provider = Column(String(32), nullable=False, default="deepseek", comment="模型供应商")
    model_name = Column(String(100), nullable=False, comment="模型名称")
    prompt_name = Column(String(50), nullable=True, comment="提示词模板类型")
    prompt_version = Column(Integer, nullable=True, comment="提示词模板版本")
    response_mode = Column(String(20), nullable=False, default="text", comment="text/json/stream")
    status = Column(String(20), nullable=False, comment="success/failed/cancelled")
    input_chars = Column(Integer, nullable=False, default=0, comment="输入字符数，不保存原文")
    output_chars = Column(Integer, nullable=False, default=0, comment="输出字符数，不保存原文")
    prompt_tokens = Column(Integer, nullable=False, default=0, comment="输入Token数")
    completion_tokens = Column(Integer, nullable=False, default=0, comment="输出Token数")
    total_tokens = Column(Integer, nullable=False, default=0, comment="总Token数")
    latency_ms = Column(Integer, nullable=False, default=0, comment="调用耗时毫秒")
    error_code = Column(String(100), nullable=True, comment="异常类型")
    error_message = Column(String(500), nullable=True, comment="脱敏后的简短错误")
