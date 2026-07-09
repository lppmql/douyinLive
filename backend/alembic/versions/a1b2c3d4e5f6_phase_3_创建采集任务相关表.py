"""Phase 3: 创建采集任务相关表 (scraper_accounts, scraper_tasks, scraper_logs)

Revision ID: a1b2c3d4e5f6
Revises: 550ffd1c12ac
Create Date: 2026-07-09 23:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '550ffd1c12ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # scraper_accounts
    op.create_table('scraper_accounts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='账号ID'),
        sa.Column('account_name', sa.String(length=50), nullable=True, comment='账号名称'),
        sa.Column('douyin_id', sa.String(length=100), nullable=True, comment='抖音号'),
        sa.Column('storage_state_path', sa.String(length=500), nullable=True, comment='浏览器状态文件路径'),
        sa.Column('user_agent', sa.String(length=500), nullable=True, comment='User-Agent'),
        sa.Column('viewport_width', sa.Integer(), nullable=True, comment='视口宽度'),
        sa.Column('viewport_height', sa.Integer(), nullable=True, comment='视口高度'),
        sa.Column('login_status', sa.String(length=20), nullable=True, server_default='never', comment='登录状态: logged_in/expired/never'),
        sa.Column('expires_at', sa.DateTime(), nullable=True, comment='登录态过期时间'),
        sa.Column('last_login_at', sa.DateTime(), nullable=True, comment='最后登录时间'),
        sa.Column('cookies_json', sa.Text(), nullable=True, comment='Cookie 备份(JSON)'),
        sa.Column('created_at', sa.DateTime(), nullable=False, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, comment='更新时间'),
        sa.PrimaryKeyConstraint('id')
    )

    # scraper_tasks
    op.create_table('scraper_tasks',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='任务ID'),
        sa.Column('account_id', sa.Integer(), nullable=True, comment='关联采集账号ID'),
        sa.Column('session_id', sa.Integer(), nullable=True, comment='关联直播场次ID'),
        sa.Column('task_type', sa.String(length=50), nullable=False, comment='任务类型: login/metrics/comments/leads/profile'),
        sa.Column('status', sa.String(length=20), nullable=True, server_default='pending', comment='状态: pending/running/completed/failed'),
        sa.Column('started_at', sa.DateTime(), nullable=True, comment='开始时间'),
        sa.Column('completed_at', sa.DateTime(), nullable=True, comment='完成时间'),
        sa.Column('error_message', sa.Text(), nullable=True, comment='错误信息'),
        sa.Column('created_at', sa.DateTime(), nullable=False, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, comment='更新时间'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_foreign_key('fk_scraper_tasks_account', 'scraper_tasks', 'scraper_accounts', ['account_id'], ['id'])
    op.create_foreign_key('fk_scraper_tasks_session', 'scraper_tasks', 'live_sessions', ['session_id'], ['id'])

    # scraper_logs
    op.create_table('scraper_logs',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='日志ID'),
        sa.Column('task_id', sa.BigInteger(), nullable=True, comment='关联任务ID'),
        sa.Column('level', sa.String(length=20), nullable=True, server_default='info', comment='级别: info/warn/error'),
        sa.Column('message', sa.Text(), nullable=True, comment='日志消息'),
        sa.Column('raw_json', sa.JSON(), nullable=True, comment='原始数据备份(JSON)'),
        sa.Column('created_at', sa.DateTime(), nullable=False, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, comment='更新时间'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_foreign_key('fk_scraper_logs_task', 'scraper_logs', 'scraper_tasks', ['task_id'], ['id'])


def downgrade() -> None:
    op.drop_table('scraper_logs')
    op.drop_table('scraper_tasks')
    op.drop_table('scraper_accounts')
