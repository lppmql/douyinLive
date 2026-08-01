"""Phase 39：评论用户公开资料缓存。

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "comment_user_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="ID"),
        sa.Column("sec_uid", sa.String(200), nullable=False, comment="评论用户稳定SecUID"),
        sa.Column("nickname", sa.String(100), nullable=True, comment="最近一次获取的公开昵称"),
        sa.Column("avatar_url", sa.String(1000), nullable=True, comment="公开头像 URL"),
        sa.Column("unique_id", sa.String(100), nullable=True, comment="用户自定义抖音号"),
        sa.Column("short_id", sa.String(100), nullable=True, comment="平台数字短号"),
        sa.Column("public_douyin_id", sa.String(100), nullable=True, comment="用于展示与匹配的首选公开抖音号"),
        sa.Column("douyin_id_type", sa.String(20), nullable=True, comment="公开抖音号类型：unique_id/short_id"),
        sa.Column("profile_source", sa.String(50), nullable=False, server_default="iesdouyin_user_info", comment="公开资料来源"),
        sa.Column("fetch_status", sa.String(20), nullable=False, server_default="pending", comment="pending/running/success/partial/failed/blocked"),
        sa.Column("last_fetched_at", sa.DateTime(), nullable=True, comment="最近完成查询时间"),
        sa.Column("retry_after", sa.DateTime(), nullable=True, comment="失败后最早重试时间"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0", comment="连续失败次数"),
        sa.Column("last_error_code", sa.String(50), nullable=True, comment="脱敏错误代码"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sec_uid", name="uq_comment_user_profiles_sec_uid"),
    )
    op.create_index("idx_comment_user_profiles_status_retry", "comment_user_profiles", ["fetch_status", "retry_after", "id"])
    op.create_index("idx_comment_user_profiles_public_id", "comment_user_profiles", ["public_douyin_id"])


def downgrade() -> None:
    op.drop_index("idx_comment_user_profiles_public_id", table_name="comment_user_profiles")
    op.drop_index("idx_comment_user_profiles_status_retry", table_name="comment_user_profiles")
    op.drop_table("comment_user_profiles")
