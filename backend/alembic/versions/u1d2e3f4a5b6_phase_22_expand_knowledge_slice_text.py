"""Expand knowledge slice content columns to LONGTEXT.

Revision ID: u1d2e3f4a5b6
Revises: t1d2e3f4a5b6
"""
from alembic import op


revision = "u1d2e3f4a5b6"
down_revision = "t1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE knowledge_time_slices
          MODIFY transcript_text LONGTEXT NULL COMMENT '本时间片真实话术',
          MODIFY comments_text LONGTEXT NULL COMMENT '本时间片真实评论',
          MODIFY search_text LONGTEXT NULL COMMENT '用于混合检索的规范化文本'
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE knowledge_time_slices
          MODIFY transcript_text TEXT NULL COMMENT '本时间片真实话术',
          MODIFY comments_text TEXT NULL COMMENT '本时间片真实评论',
          MODIFY search_text TEXT NULL COMMENT '用于混合检索的规范化文本'
    """)
