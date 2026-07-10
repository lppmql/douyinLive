"""Phase 12: 记录直播详情采集状态，避免重复重试不可回放场次"""

from alembic import op
import sqlalchemy as sa


revision = "k1d2e3f4a5b6"
down_revision = "j1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "live_sessions",
        sa.Column("detail_collection_status", sa.String(20), nullable=True, server_default="pending", comment="详情采集状态"),
    )
    op.add_column(
        "live_sessions",
        sa.Column("detail_collection_error", sa.String(500), nullable=True, comment="详情采集最近错误"),
    )


def downgrade() -> None:
    op.drop_column("live_sessions", "detail_collection_error")
    op.drop_column("live_sessions", "detail_collection_status")
