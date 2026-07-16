"""Expand complete transcript content to LONGTEXT.

Revision ID: y1d2e3f4a5b6
Revises: x1d2e3f4a5b6
"""
from alembic import op


revision = "y1d2e3f4a5b6"
down_revision = "x1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE transcript_full_texts
          MODIFY full_text LONGTEXT NULL COMMENT '完整拼接话术'
        """
    )
    op.execute(
        """
        UPDATE asr_tasks AS task
        SET status = 'queued',
            retry_count = 0,
            error_message = NULL,
            started_at = NULL,
            completed_at = NULL,
            worker_id = NULL,
            heartbeat_at = NULL
        WHERE task.status = 'failed'
          AND EXISTS (
              SELECT 1
              FROM asr_audio_chunks AS chunk
              WHERE chunk.task_id = task.id
          )
          AND NOT EXISTS (
              SELECT 1
              FROM asr_audio_chunks AS chunk
              WHERE chunk.task_id = task.id
                AND chunk.status <> 'completed'
          )
          AND EXISTS (
              SELECT 1
              FROM transcript_segments AS segment
              WHERE segment.session_id = task.session_id
          )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE transcript_full_texts
          MODIFY full_text TEXT NULL COMMENT '完整拼接话术'
        """
    )
