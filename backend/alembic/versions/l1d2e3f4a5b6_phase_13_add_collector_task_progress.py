"""phase 13 add collector task progress

Revision ID: l1d2e3f4a5b6
Revises: k1d2e3f4a5b6
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "l1d2e3f4a5b6"
down_revision: Union[str, None] = "k1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scraper_tasks", sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0", comment="任务进度百分比"))
    op.add_column("scraper_tasks", sa.Column("progress_current", sa.Integer(), nullable=False, server_default="0", comment="当前完成数量"))
    op.add_column("scraper_tasks", sa.Column("progress_total", sa.Integer(), nullable=False, server_default="0", comment="预计总数量"))
    op.add_column("scraper_tasks", sa.Column("progress_stage", sa.String(length=50), nullable=True, comment="当前执行阶段"))
    op.add_column("scraper_tasks", sa.Column("progress_message", sa.String(length=500), nullable=True, comment="当前进度说明"))


def downgrade() -> None:
    op.drop_column("scraper_tasks", "progress_message")
    op.drop_column("scraper_tasks", "progress_stage")
    op.drop_column("scraper_tasks", "progress_total")
    op.drop_column("scraper_tasks", "progress_current")
    op.drop_column("scraper_tasks", "progress_percent")
