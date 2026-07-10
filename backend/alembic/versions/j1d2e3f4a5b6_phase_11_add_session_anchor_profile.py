"""Phase 11: 保存场次级主播资料，修复企业主账号历史场次串主播"""

from alembic import op
import sqlalchemy as sa


revision = "j1d2e3f4a5b6"
down_revision = "i1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("live_sessions", sa.Column("anchor_name", sa.String(100), nullable=True, comment="本场主播名称"))
    op.add_column("live_sessions", sa.Column("anchor_nickname", sa.String(100), nullable=True, comment="本场主播昵称"))
    op.add_column("live_sessions", sa.Column("anchor_avatar_url", sa.String(500), nullable=True, comment="本场主播头像"))
    op.add_column("live_sessions", sa.Column("douyin_id", sa.String(100), nullable=True, comment="本场主播抖音号"))
    op.add_column("live_sessions", sa.Column("douyin_uid", sa.String(100), nullable=True, comment="本场主播抖音UID"))


def downgrade() -> None:
    for name in ("douyin_uid", "douyin_id", "anchor_avatar_url", "anchor_nickname", "anchor_name"):
        op.drop_column("live_sessions", name)
