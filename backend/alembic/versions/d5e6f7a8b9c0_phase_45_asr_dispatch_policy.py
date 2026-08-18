"""phase 45 ASR dispatch policy and manual queue source

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "asr_tasks",
        sa.Column(
            "queue_source",
            sa.String(20),
            nullable=False,
            server_default="auto",
            comment="排队来源: auto/manual",
        ),
    )
    op.create_index(
        "idx_asr_tasks_source_status_priority",
        "asr_tasks",
        ["queue_source", "status", "priority"],
    )
    op.create_table(
        "asr_dispatch_policies",
        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=False,
            nullable=False,
            comment="固定单例ID",
        ),
        sa.Column(
            "order_mode",
            sa.String(20),
            nullable=False,
            server_default="smart",
            comment="自动队列排序: smart/latest/fifo",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="更新时间",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        sa.text(
            "INSERT INTO asr_dispatch_policies (id, order_mode, created_at, updated_at) "
            "VALUES (1, 'smart', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
    )


def downgrade() -> None:
    op.drop_table("asr_dispatch_policies")
    op.drop_index("idx_asr_tasks_source_status_priority", table_name="asr_tasks")
    op.drop_column("asr_tasks", "queue_source")
