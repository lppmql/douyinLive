"""phone_varchar_100

Revision ID: c2dcb33b3a36
Revises: c9d0e1f2a3b4
Create Date: 2026-07-27 21:57:18.453435

仅放宽 leads.lead_phone 字段长度，容纳含空格/多号码的原始客资。
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = 'c2dcb33b3a36'
down_revision: Union[str, None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """把 lead_phone 从 VARCHAR(20) 放宽到 VARCHAR(100)。"""
    op.alter_column(
        'leads',
        'lead_phone',
        existing_type=mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=20),
        type_=sa.String(length=100),
        comment='手机号（放宽以便容纳含空格/多号码的原始客资）',
        existing_comment='手机号',
        existing_nullable=True,
    )


def downgrade() -> None:
    """回退到 VARCHAR(20)，超长数据会被截断。"""
    op.alter_column(
        'leads',
        'lead_phone',
        existing_type=sa.String(length=100),
        type_=mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=20),
        comment='手机号',
        existing_comment='手机号（放宽以便容纳含空格/多号码的原始客资）',
        existing_nullable=True,
    )
