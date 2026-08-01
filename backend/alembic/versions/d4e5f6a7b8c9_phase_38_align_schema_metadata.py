"""对齐 ORM 与历史迁移中的字段元数据。

Revision ID: d4e5f6a7b8c9
Revises: 12bd80d81073
Create Date: 2026-08-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "12bd80d81073"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "asr_tasks",
        "postprocess_status",
        existing_type=sa.String(length=20),
        existing_nullable=False,
        existing_server_default=sa.text("'pending'"),
        comment="后处理状态: pending/processing/completed/failed/skipped",
    )
    op.alter_column(
        "leads",
        "lead_source",
        existing_type=sa.String(length=50),
        existing_nullable=True,
        comment="业务来源：私信/小风车/表单/评论",
    )


def downgrade() -> None:
    op.alter_column(
        "leads",
        "lead_source",
        existing_type=sa.String(length=50),
        existing_nullable=True,
        comment="来源：私信/小风车/表单/评论",
    )
    op.alter_column(
        "asr_tasks",
        "postprocess_status",
        existing_type=sa.String(length=20),
        existing_nullable=False,
        existing_server_default=sa.text("'pending'"),
        comment="后处理状态: pending/processing/completed/failed",
    )
