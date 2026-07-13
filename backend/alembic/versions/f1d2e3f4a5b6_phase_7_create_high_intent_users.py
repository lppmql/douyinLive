"""Phase 7: create high_intent_users

Revision ID: f1d2e3f4a5b6
Revises: e1d2e3f4a5b6
Create Date: 2026-07-10 14:05:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = 'f1d2e3f4a5b6'
down_revision: Union[str, None] = 'e1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = 'e1d2e3f4a5b6'


def upgrade() -> None:
    op.create_table('high_intent_users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='ID'),
        sa.Column('session_id', sa.Integer(), nullable=False, comment='关联直播场次ID'),
        sa.Column('comment_id', sa.BigInteger(), nullable=True, comment='关联评论ID'),
        sa.Column('user_name', sa.String(length=100), nullable=True, comment='用户昵称'),
        sa.Column('phone', sa.String(length=20), nullable=True, comment='手机号（脱敏）'),
        sa.Column('product_interest', sa.String(length=200), nullable=True, comment='感兴趣的产品/服务'),
        sa.Column('intent_level', sa.String(length=20), nullable=True, comment='意向等级：high/medium/low'),
        sa.Column('intent_reason', sa.Text(), nullable=True, comment='AI判断依据'),
        sa.Column('is_contacted', sa.Integer(), nullable=True, comment='是否已联系：1是 0否'),
        sa.Column('contacted_at', sa.DateTime(), nullable=True, comment='联系时间'),
        sa.Column('contact_note', sa.Text(), nullable=True, comment='联系备注'),
        sa.Column('created_at', sa.DateTime(), nullable=False, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, comment='更新时间'),
        sa.ForeignKeyConstraint(['comment_id'], ['comments.id'], ),
        sa.ForeignKeyConstraint(['session_id'], ['live_sessions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('high_intent_users')
