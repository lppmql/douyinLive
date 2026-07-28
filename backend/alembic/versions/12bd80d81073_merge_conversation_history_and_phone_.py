"""Merge conversation history and phone varchar heads

Revision ID: 12bd80d81073
Revises: a2d3e4f5a6b7, c2dcb33b3a36
Create Date: 2026-07-28 13:44:03.497520

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '12bd80d81073'
down_revision: Union[str, None] = ('a2d3e4f5a6b7', 'c2dcb33b3a36')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
