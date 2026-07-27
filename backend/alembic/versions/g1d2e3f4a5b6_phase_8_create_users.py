"""Phase 8: 创建用户表 (users)

Revision ID: g1d2e3f4a5b6
Revises: f2d3e4f5a6b7
Create Date: 2026-07-10 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'g1d2e3f4a5b6'
down_revision: Union[str, None] = 'f2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 创建 users 表
    op.create_table('users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='用户ID'),
        sa.Column('username', sa.String(length=64), nullable=False, comment='用户名'),
        sa.Column('password_hash', sa.String(length=256), nullable=False, comment='密码哈希（bcrypt）'),
        sa.Column('nickname', sa.String(length=64), nullable=True, server_default='', comment='昵称'),
        sa.Column('email', sa.String(length=128), nullable=True, server_default='', comment='邮箱'),
        sa.Column('phone', sa.String(length=20), nullable=True, server_default='', comment='手机号'),
        sa.Column('avatar', sa.String(length=256), nullable=True, server_default='', comment='头像 URL'),
        sa.Column('roles', sa.JSON(), nullable=True, comment='角色列表'),
        sa.Column('status', sa.String(length=20), nullable=True, server_default='active', comment='状态: active / disabled'),
        sa.Column('last_login_at', sa.DateTime(), nullable=True, comment='最后登录时间'),
        sa.Column('created_at', sa.DateTime(), nullable=False, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, comment='更新时间'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username', name='uq_users_username')
    )

    # 不创建固定密码账号。全新安装由启动流程读取根目录 .env 中的
    # BOOTSTRAP_ADMIN_USERNAME / BOOTSTRAP_ADMIN_PASSWORD 安全初始化管理员。


def downgrade() -> None:
    op.drop_table('users')
