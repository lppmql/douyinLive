"""Add conversation history tables for knowledge base chat.

Revision ID: a2d3e4f5a6b7
Revises: z1d2e3f4a5b6
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import JSON


revision = "a2d3e4f5a6b7"
down_revision = "z1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建对话历史的两张表"""
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="对话ID"),
        sa.Column("title", sa.String(length=200), nullable=True, comment="对话标题（自动取首条问题前50字）"),
        sa.Column("message_count", sa.Integer(), server_default="0", comment="消息条数（冗余字段，方便列表展示）"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="消息ID"),
        sa.Column(
            "conversation_id",
            sa.Integer(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
            comment="所属对话ID",
        ),
        sa.Column("role", sa.String(length=20), nullable=False, comment="角色：user / assistant"),
        sa.Column("content", sa.Text(), nullable=False, comment="消息内容"),
        sa.Column("sources", JSON(), nullable=True, comment="引用来源列表（仅 assistant 消息）"),
        sa.Column(
            "feedback",
            sa.String(length=10),
            nullable=True,
            comment="用户反馈：like / dislike / null",
        ),
        sa.Column(
            "error",
            sa.Integer(),
            server_default="0",
            comment="是否错误消息：0=正常 1=出错",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
    )
    # 按对话ID+消息时间排序的联合索引，加速消息列表查询
    op.create_index("ix_conversation_messages_conv_id", "conversation_messages", ["conversation_id", "id"])


def downgrade() -> None:
    """删除对话历史表"""
    op.drop_index("ix_conversation_messages_conv_id", table_name="conversation_messages")
    op.drop_table("conversation_messages")
    op.drop_table("conversations")
