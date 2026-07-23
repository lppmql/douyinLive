"""Phase 34：补充评论用户头像与公开抖音号。

Revision ID: 7e4b9c2d1a66
Revises: 5c8e2a7f9b11
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa


revision = "7e4b9c2d1a66"
down_revision = "5c8e2a7f9b11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """只增加可空资料字段，旧评论不受影响，重新采集后按真实接口数据回填。"""
    op.add_column(
        "comments",
        sa.Column("user_avatar_url", sa.String(length=1000), nullable=True, comment="评论用户头像 URL"),
    )
    op.add_column(
        "comments",
        sa.Column("user_douyin_id", sa.String(length=100), nullable=True, comment="评论用户公开抖音号"),
    )


def downgrade() -> None:
    """回滚字段结构，不删除评论主体数据。"""
    op.drop_column("comments", "user_douyin_id")
    op.drop_column("comments", "user_avatar_url")
