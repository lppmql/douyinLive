"""Phase 5: 创建 ASR 转写任务表 (asr_tasks)

Revision ID: c1d2e3f4a5b6
Revises: b1c2d3e4f5a6
Create Date: 2026-07-10 00:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('asr_tasks',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='任务ID'),
        sa.Column('session_id', sa.Integer(), nullable=False, comment='关联直播场次'),
        sa.Column('stream_id', sa.Integer(), nullable=True, comment='关联流源'),
        sa.Column('status', sa.String(length=20), nullable=True, server_default='queued', comment='状态: queued/processing/completed/failed'),
        sa.Column('task_type', sa.String(length=20), nullable=True, server_default='realtime', comment='任务类型: realtime/offline'),
        sa.Column('started_at', sa.DateTime(), nullable=True, comment='开始时间'),
        sa.Column('completed_at', sa.DateTime(), nullable=True, comment='完成时间'),
        sa.Column('error_message', sa.Text(), nullable=True, comment='错误信息'),
        sa.Column('created_at', sa.DateTime(), nullable=False, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, comment='更新时间'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_foreign_key('fk_asr_tasks_session', 'asr_tasks', 'live_sessions', ['session_id'], ['id'])
    op.create_foreign_key('fk_asr_tasks_stream', 'asr_tasks', 'stream_sources', ['stream_id'], ['id'])


def downgrade() -> None:
    op.drop_table('asr_tasks')
