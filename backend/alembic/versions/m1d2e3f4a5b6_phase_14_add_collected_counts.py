"""phase 14 add collected anchor and session counts

Revision ID: m1d2e3f4a5b6
Revises: l1d2e3f4a5b6
"""

from alembic import op
import sqlalchemy as sa


revision = "m1d2e3f4a5b6"
down_revision = "l1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scraper_tasks",
        sa.Column(
            "collected_anchor_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="本次已采集主播数",
        ),
    )
    op.add_column(
        "scraper_tasks",
        sa.Column(
            "collected_session_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="本次已采集直播场次数",
        ),
    )


def downgrade() -> None:
    op.drop_column("scraper_tasks", "collected_session_count")
    op.drop_column("scraper_tasks", "collected_anchor_count")
