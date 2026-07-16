"""Optimize the default live-session list ordering.

Revision ID: c2d2e3f4a5b6
Revises: b2d2e3f4a5b6
"""
from alembic import op


revision = "c2d2e3f4a5b6"
down_revision = "b2d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_live_sessions_start_id",
        "live_sessions",
        ["live_start_time", "id"],
    )


def downgrade() -> None:
    op.drop_index("idx_live_sessions_start_id", table_name="live_sessions")
