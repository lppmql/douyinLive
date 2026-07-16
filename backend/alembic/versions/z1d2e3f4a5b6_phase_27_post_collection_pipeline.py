"""Add recoverable post-collection pipeline state.

Revision ID: z1d2e3f4a5b6
Revises: y1d2e3f4a5b6
"""
from alembic import op
import sqlalchemy as sa


revision = "z1d2e3f4a5b6"
down_revision = "y1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "asr_tasks",
        sa.Column(
            "postprocess_status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
            comment="后处理状态: pending/processing/completed/failed",
        ),
    )
    op.add_column(
        "asr_tasks",
        sa.Column("postprocess_started_at", sa.DateTime(), nullable=True, comment="话术评分与复盘处理开始时间"),
    )
    op.add_column(
        "asr_tasks",
        sa.Column("postprocess_completed_at", sa.DateTime(), nullable=True, comment="知识库同步完成时间"),
    )
    op.add_column(
        "asr_tasks",
        sa.Column("postprocess_error", sa.Text(), nullable=True, comment="后处理失败或降级原因"),
    )
    op.add_column(
        "asr_tasks",
        sa.Column(
            "postprocess_attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="后处理执行次数",
        ),
    )
    op.add_column(
        "asr_tasks",
        sa.Column("postprocess_result", sa.JSON(), nullable=True, comment="话术、复盘、知识库和DataEase处理结果"),
    )
    op.create_index(
        "idx_asr_tasks_postprocess_status",
        "asr_tasks",
        ["postprocess_status", "postprocess_attempt_count"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_asr_tasks_postprocess_status", table_name="asr_tasks")
    op.drop_column("asr_tasks", "postprocess_result")
    op.drop_column("asr_tasks", "postprocess_attempt_count")
    op.drop_column("asr_tasks", "postprocess_error")
    op.drop_column("asr_tasks", "postprocess_completed_at")
    op.drop_column("asr_tasks", "postprocess_started_at")
    op.drop_column("asr_tasks", "postprocess_status")
