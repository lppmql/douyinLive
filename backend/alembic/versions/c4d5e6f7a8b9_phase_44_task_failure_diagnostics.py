"""phase 44 task failure diagnostics

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scraper_tasks", sa.Column("error_code", sa.String(50), nullable=True, comment="结构化错误码"))
    op.add_column("scraper_tasks", sa.Column("failure_stage", sa.String(50), nullable=True, comment="失败发生阶段"))
    op.add_column("scraper_tasks", sa.Column("is_retryable", sa.Boolean(), nullable=True, comment="失败是否适合自动或人工重试"))


def downgrade() -> None:
    op.drop_column("scraper_tasks", "is_retryable")
    op.drop_column("scraper_tasks", "failure_stage")
    op.drop_column("scraper_tasks", "error_code")
