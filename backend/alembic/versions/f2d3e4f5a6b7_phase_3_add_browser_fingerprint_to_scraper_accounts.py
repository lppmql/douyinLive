"""Phase 3: 为 scraper_accounts 增加浏览器指纹快照字段

Revision ID: f2d3e4f5a6b7
Revises: f1d2e3f4a5b6
Create Date: 2026-07-10 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2d3e4f5a6b7'
down_revision: Union[str, None] = 'f1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'scraper_accounts',
        sa.Column('browser_fingerprint_json', sa.Text(), nullable=True, comment='浏览器指纹快照(JSON)')
    )


def downgrade() -> None:
    op.drop_column('scraper_accounts', 'browser_fingerprint_json')
