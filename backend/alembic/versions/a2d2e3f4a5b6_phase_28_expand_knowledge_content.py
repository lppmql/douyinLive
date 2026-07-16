"""Expand knowledge content and retry overflowed post-processing.

Revision ID: a2d2e3f4a5b6
Revises: z1d2e3f4a5b6
"""
from alembic import op


revision = "a2d2e3f4a5b6"
down_revision = "z1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE knowledge_base
          MODIFY content LONGTEXT NULL COMMENT '内容'
        """
    )
    op.execute(
        """
        UPDATE asr_tasks
        SET postprocess_status = 'pending',
            postprocess_attempt_count = 0,
            postprocess_started_at = NULL,
            postprocess_completed_at = NULL
        WHERE postprocess_status = 'failed'
          AND postprocess_error LIKE '%Data too long for column%content%'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE knowledge_base
          MODIFY content TEXT NULL COMMENT '内容'
        """
    )
