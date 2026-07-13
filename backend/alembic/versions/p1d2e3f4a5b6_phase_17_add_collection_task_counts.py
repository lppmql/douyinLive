"""phase 17 add collection task counts

Revision ID: p1d2e3f4a5b6
Revises: o1d2e3f4a5b6
"""
from alembic import op
import sqlalchemy as sa


revision = "p1d2e3f4a5b6"
down_revision = "o1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, comment in (
        ("new_session_count", "本次新增场次数"),
        ("mapped_session_count", "本次更新主播映射场次数"),
        ("checked_detail_count", "本次已检查详情场次数"),
        ("refreshed_detail_count", "本次已补齐详情场次数"),
        ("failed_detail_count", "本次详情采集失败场次数"),
        ("remaining_detail_count", "待补齐详情场次数"),
    ):
        op.add_column("scraper_tasks", sa.Column(name, sa.Integer(), nullable=False, server_default="0", comment=comment))


def downgrade() -> None:
    for name in (
        "remaining_detail_count", "failed_detail_count", "refreshed_detail_count",
        "checked_detail_count", "mapped_session_count", "new_session_count",
    ):
        op.drop_column("scraper_tasks", name)
