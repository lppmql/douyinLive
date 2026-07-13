"""phase 16 add comment user identity

Revision ID: o1d2e3f4a5b6
Revises: n1d2e3f4a5b6
"""
from alembic import op
import sqlalchemy as sa


revision = "o1d2e3f4a5b6"
down_revision = "n1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("comments", sa.Column("user_sec_uid", sa.String(length=200), nullable=True, comment="评论用户稳定SecUID"))
    op.add_column("comments", sa.Column("webcast_uid", sa.String(length=200), nullable=True, comment="本条评论Webcast用户标识"))


def downgrade() -> None:
    op.drop_column("comments", "webcast_uid")
    op.drop_column("comments", "user_sec_uid")
