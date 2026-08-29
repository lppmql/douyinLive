"""为知识库对话增加真实场次归属。

Revision ID: g8c9d0e1f2a3
Revises: f7a8b9c0d1e2
Create Date: 2026-08-29
"""

from alembic import op
import sqlalchemy as sa


revision = "g8c9d0e1f2a3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """空场次表示原有的全知识库对话，历史数据无需猜测或回填。"""
    op.add_column(
        "conversations",
        sa.Column(
            "session_id",
            sa.Integer(),
            nullable=True,
            comment="知识问答限定场次；空值表示全知识库",
        ),
    )
    op.create_index("ix_conversations_session_id", "conversations", ["session_id"])
    op.create_foreign_key(
        "fk_conversations_session_id_live_sessions",
        "conversations",
        "live_sessions",
        ["session_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_conversations_session_id_live_sessions",
        "conversations",
        type_="foreignkey",
    )
    op.drop_index("ix_conversations_session_id", table_name="conversations")
    op.drop_column("conversations", "session_id")
