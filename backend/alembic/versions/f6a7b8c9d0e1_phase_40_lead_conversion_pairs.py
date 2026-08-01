"""Phase 40：同主播一分钟客资配对。

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lead_conversion_pairs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="配对ID"),
        sa.Column("douyin_lead_id", sa.Integer(), nullable=False, comment="提供客户抖音号的原始记录ID"),
        sa.Column("contact_lead_id", sa.Integer(), nullable=False, comment="提供手机号或微信号的原始记录ID"),
        sa.Column("session_id", sa.Integer(), nullable=True, comment="按主播和抖音号归属的直播场次ID"),
        sa.Column("anchor_name", sa.String(100), nullable=False, comment="两条原始记录共同的主播维度"),
        sa.Column("douyin_id", sa.String(100), nullable=False, comment="客户公开抖音号"),
        sa.Column("contact_type", sa.String(20), nullable=False, comment="联系方式类型：phone/wechat"),
        sa.Column("contact_value", sa.String(100), nullable=False, comment="真实手机号或微信号"),
        sa.Column("douyin_recorded_at", sa.DateTime(), nullable=False, comment="抖音号原始记录时间"),
        sa.Column("contact_recorded_at", sa.DateTime(), nullable=False, comment="联系方式原始记录时间"),
        sa.Column("converted_at", sa.DateTime(), nullable=False, comment="两项资料均完成的时间"),
        sa.Column("gap_seconds", sa.Integer(), nullable=False, comment="两条记录绝对时间差秒数"),
        sa.Column("attribution_status", sa.String(20), nullable=False, server_default="paired", comment="paired/attributed"),
        sa.Column("attribution_method", sa.String(50), nullable=False, server_default="anchor_60s_pair", comment="配对与场次归属依据"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), comment="更新时间"),
        sa.ForeignKeyConstraint(["contact_lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["douyin_lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["live_sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contact_lead_id", name="uq_lead_conversion_pairs_contact"),
        sa.UniqueConstraint("douyin_lead_id", name="uq_lead_conversion_pairs_douyin"),
    )
    op.create_index("idx_lead_conversion_pairs_session_time", "lead_conversion_pairs", ["session_id", "converted_at", "id"])
    op.create_index("idx_lead_conversion_pairs_douyin_id", "lead_conversion_pairs", ["douyin_id"])


def downgrade() -> None:
    op.drop_index("idx_lead_conversion_pairs_douyin_id", table_name="lead_conversion_pairs")
    op.drop_index("idx_lead_conversion_pairs_session_time", table_name="lead_conversion_pairs")
    op.drop_table("lead_conversion_pairs")
