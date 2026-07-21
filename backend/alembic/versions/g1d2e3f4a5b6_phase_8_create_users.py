"""Phase 8: 创建用户表 (users)

Revision ID: g1d2e3f4a5b6
Revises: f2d3e4f5a6b7
Create Date: 2026-07-10 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# 使用 bcrypt 直接生成密码哈希（避免 passlib 与 bcrypt 5.x 兼容问题）
import bcrypt as _bcrypt

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

    # 插入默认管理员账号 (admin / Admin123456)
    admin_pwd = _bcrypt.hashpw(b"Admin123456", _bcrypt.gensalt()).decode()
    op.execute(
        sa.text("""
            INSERT INTO users (username, password_hash, nickname, roles, status, created_at, updated_at)
            VALUES ('admin', :pwd, '系统管理员', :roles, 'active', NOW(), NOW())
        """).bindparams(pwd=admin_pwd, roles='["R_SUPER"]')
    )

    # 插入默认普通用户 (user / User123456)
    user_pwd = _bcrypt.hashpw(b"User123456", _bcrypt.gensalt()).decode()
    op.execute(
        sa.text("""
            INSERT INTO users (username, password_hash, nickname, roles, status, created_at, updated_at)
            VALUES ('user', :pwd, '普通用户', :roles, 'active', NOW(), NOW())
        """).bindparams(pwd=user_pwd, roles='["R_USER"]')
    )


def downgrade() -> None:
    op.drop_table('users')
