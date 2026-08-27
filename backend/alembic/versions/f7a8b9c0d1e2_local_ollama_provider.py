"""AI 调用追踪默认供应商改为本地 Ollama。

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-08-26
"""

from alembic import op
import sqlalchemy as sa


revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """只修改新记录的默认值，历史供应商记录保持真实原值。"""
    op.alter_column(
        "ai_call_traces",
        "provider",
        existing_type=sa.String(length=32),
        existing_nullable=False,
        server_default="ollama",
    )


def downgrade() -> None:
    """回退默认值，不改写任何历史调用记录。"""
    op.alter_column(
        "ai_call_traces",
        "provider",
        existing_type=sa.String(length=32),
        existing_nullable=False,
        server_default="deepseek",
    )
