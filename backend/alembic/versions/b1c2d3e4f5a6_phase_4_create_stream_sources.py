"""Phase 4: 创建直播流源表 (stream_sources)

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-07-09 23:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('stream_sources',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='流源ID'),
        sa.Column('session_id', sa.Integer(), nullable=False, comment='关联直播场次'),
        sa.Column('source_type', sa.String(length=20), nullable=True, server_default='m3u8', comment='流源类型: m3u8/flv/hls'),
        sa.Column('m3u8_url', sa.String(length=2000), nullable=False, comment='m3u8 播放地址'),
        sa.Column('headers_json', sa.JSON(), nullable=True, comment='请求头(Referer/User-Agent等)'),
        sa.Column('quality', sa.String(length=20), nullable=True, comment='清晰度: origin/uhd/hd/sd'),
        sa.Column('status', sa.String(length=20), nullable=True, server_default='active', comment='状态: active/expired/error'),
        sa.Column('expires_at', sa.DateTime(), nullable=True, comment='过期时间'),
        sa.Column('fetched_at', sa.DateTime(), nullable=True, comment='采集时间'),
        sa.Column('created_at', sa.DateTime(), nullable=False, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, comment='更新时间'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_foreign_key('fk_stream_sources_session', 'stream_sources', 'live_sessions', ['session_id'], ['id'])


def downgrade() -> None:
    op.drop_table('stream_sources')
