"""phase_37_实时初稿跳过最终复盘

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-27
"""

from alembic import op
import sqlalchemy as sa


revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """历史实时任务只代表直播初稿，不能继续等待最终 AI 复盘。"""
    op.execute(
        sa.text(
            """
            UPDATE asr_tasks
            SET postprocess_status = 'skipped'
            WHERE task_type = 'realtime'
              AND postprocess_status IN ('pending', 'failed')
            """
        )
    )


def downgrade() -> None:
    """回退旧行为时，仅把实时任务的 skipped 恢复为 pending。"""
    op.execute(
        sa.text(
            """
            UPDATE asr_tasks
            SET postprocess_status = 'pending'
            WHERE task_type = 'realtime'
              AND postprocess_status = 'skipped'
            """
        )
    )
