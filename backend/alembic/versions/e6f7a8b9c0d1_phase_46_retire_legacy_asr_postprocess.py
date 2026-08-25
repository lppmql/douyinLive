"""phase 46：停用旧 ASR 自动后处理积压。

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-08-25
"""

from alembic import op
import sqlalchemy as sa


revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None

_RETIRE_REASON = (
    "旧自动后处理已停用：AI复盘改为人工生成，知识库与DataEase独立同步"
)


def upgrade() -> None:
    """只清理从未尝试过的历史积压，保留已执行结果和真实失败记录。"""
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE asr_tasks
            SET postprocess_status = 'skipped',
                postprocess_error = :reason,
                postprocess_started_at = NULL,
                postprocess_completed_at = NULL
            WHERE postprocess_status = 'pending'
              AND postprocess_attempt_count = 0
            """
        ),
        {"reason": _RETIRE_REASON},
    )


def downgrade() -> None:
    """仅恢复由本迁移明确标记的记录，避免改动其它 skipped 任务。"""
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE asr_tasks
            SET postprocess_status = 'pending',
                postprocess_error = NULL
            WHERE postprocess_status = 'skipped'
              AND postprocess_error = :reason
              AND postprocess_attempt_count = 0
            """
        ),
        {"reason": _RETIRE_REASON},
    )
