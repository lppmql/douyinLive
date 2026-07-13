"""Phase 7: create prompt_templates

Revision ID: e1d2e3f4a5b6
Revises: d1d2e3f4a5b6
Create Date: 2026-07-10 13:48:36.998076

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e1d2e3f4a5b6'
down_revision: Union[str, None] = 'd1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = 'd1d2e3f4a5b6'


def upgrade() -> None:
    op.create_table('prompt_templates',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='ID'),
        sa.Column('type', sa.String(length=50), nullable=False, comment='类型：speech_score/trend_analysis/anomaly/optimization/qa'),
        sa.Column('name', sa.String(length=100), nullable=True, comment='模板名称'),
        sa.Column('content', sa.Text(), nullable=False, comment='提示词内容（含变量占位符）'),
        sa.Column('version', sa.Integer(), nullable=False, comment='版本号'),
        sa.Column('description', sa.String(length=500), nullable=True, comment='用途说明'),
        sa.Column('created_at', sa.DateTime(), nullable=False, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, comment='更新时间'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_prompt_templates_type'), 'prompt_templates', ['type'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_prompt_templates_type'), table_name='prompt_templates')
    op.drop_table('prompt_templates')
