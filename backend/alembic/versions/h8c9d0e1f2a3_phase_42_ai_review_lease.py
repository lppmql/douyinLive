"""Phase 42：统一AI复盘跨进程任务租约。

Revision ID: h8c9d0e1f2a3
Revises: g7b8c9d0e1f2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "h8c9d0e1f2a3"
down_revision: str | None = "g7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "unified_ai_review_runs",
        sa.Column("generation_token", sa.String(36), nullable=True, comment="跨进程生成任务租约令牌"),
    )
    op.add_column(
        "unified_ai_review_runs",
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True, comment="生成任务租约过期时间"),
    )


def downgrade() -> None:
    op.drop_column("unified_ai_review_runs", "lease_expires_at")
    op.drop_column("unified_ai_review_runs", "generation_token")
