"""Add lightweight AI call observability.

Revision ID: d2d2e3f4a5b6
Revises: c2d2e3f4a5b6
"""
from alembic import op
import sqlalchemy as sa


revision = "d2d2e3f4a5b6"
down_revision = "c2d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_call_traces",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="AI调用ID"),
        sa.Column("trace_id", sa.String(128), nullable=False, comment="应用链路追踪ID"),
        sa.Column("session_id", sa.Integer(), nullable=True, comment="关联真实直播场次"),
        sa.Column("operation", sa.String(50), nullable=False, comment="业务操作类型"),
        sa.Column("provider", sa.String(32), server_default="deepseek", nullable=False, comment="模型供应商"),
        sa.Column("model_name", sa.String(100), nullable=False, comment="模型名称"),
        sa.Column("prompt_name", sa.String(50), nullable=True, comment="提示词模板类型"),
        sa.Column("prompt_version", sa.Integer(), nullable=True, comment="提示词模板版本"),
        sa.Column("response_mode", sa.String(20), server_default="text", nullable=False, comment="text/json/stream"),
        sa.Column("status", sa.String(20), nullable=False, comment="success/failed/cancelled"),
        sa.Column("input_chars", sa.Integer(), server_default="0", nullable=False, comment="输入字符数，不保存原文"),
        sa.Column("output_chars", sa.Integer(), server_default="0", nullable=False, comment="输出字符数，不保存原文"),
        sa.Column("prompt_tokens", sa.Integer(), server_default="0", nullable=False, comment="输入Token数"),
        sa.Column("completion_tokens", sa.Integer(), server_default="0", nullable=False, comment="输出Token数"),
        sa.Column("total_tokens", sa.Integer(), server_default="0", nullable=False, comment="总Token数"),
        sa.Column("latency_ms", sa.Integer(), server_default="0", nullable=False, comment="调用耗时毫秒"),
        sa.Column("error_code", sa.String(100), nullable=True, comment="异常类型"),
        sa.Column("error_message", sa.String(500), nullable=True, comment="脱敏后的简短错误"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["live_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_ai_call_trace_trace", "ai_call_traces", ["trace_id"])
    op.create_index("idx_ai_call_trace_session_created", "ai_call_traces", ["session_id", "created_at"])
    op.create_index(
        "idx_ai_call_trace_operation_status",
        "ai_call_traces",
        ["operation", "status", "created_at"],
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW de_v_fact_ai_call_trace AS
        SELECT id AS ai_call_id, trace_id, session_id, operation, provider,
               model_name, prompt_name, prompt_version, response_mode, status,
               input_chars, output_chars, prompt_tokens, completion_tokens,
               total_tokens, latency_ms, error_code, created_at AS observed_at
        FROM ai_call_traces
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS de_v_fact_ai_call_trace")
    op.drop_index("idx_ai_call_trace_operation_status", table_name="ai_call_traces")
    op.drop_index("idx_ai_call_trace_session_created", table_name="ai_call_traces")
    op.drop_index("idx_ai_call_trace_trace", table_name="ai_call_traces")
    op.drop_table("ai_call_traces")
