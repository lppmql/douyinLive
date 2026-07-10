"""Phase 9: 为 live_rooms 增加主播资料字段

Revision ID: h1d2e3f4a5b6
Revises: g1d2e3f4a5b6
Create Date: 2026-07-10 21:10:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "h1d2e3f4a5b6"
down_revision = "g1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("live_rooms", sa.Column("anchor_nickname", sa.String(length=100), nullable=True, comment="主播昵称/展示名"))
    op.add_column("live_rooms", sa.Column("anchor_avatar_url", sa.String(length=500), nullable=True, comment="主播头像 URL"))
    op.add_column("live_rooms", sa.Column("douyin_uid", sa.String(length=100), nullable=True, comment="抖音 UID"))


def downgrade() -> None:
    op.drop_column("live_rooms", "douyin_uid")
    op.drop_column("live_rooms", "anchor_avatar_url")
    op.drop_column("live_rooms", "anchor_nickname")
