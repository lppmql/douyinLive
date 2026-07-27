"""phase_36_kezi_lead_sync

Revision ID: b8c9d0e1f2a3
Revises: a7d8e9f0b1c2
Create Date: 2026-07-27
"""

from alembic import op
import sqlalchemy as sa


revision = "b8c9d0e1f2a3"
down_revision = "a7d8e9f0b1c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """增加外部唯一编号、待归属状态和持久同步游标。"""
    op.alter_column(
        "leads",
        "session_id",
        existing_type=sa.Integer(),
        nullable=True,
        existing_comment="关联直播场次ID",
        comment="真实匹配的直播场次ID",
    )
    op.add_column("leads", sa.Column("douyin_id", sa.String(100), nullable=True, comment="客户抖音号"))
    op.add_column("leads", sa.Column("anchor_name", sa.String(100), nullable=True, comment="客资提交时记录的主播"))
    op.add_column("leads", sa.Column("external_source", sa.String(50), nullable=True, comment="外部数据系统标识"))
    op.add_column("leads", sa.Column("external_id", sa.BigInteger(), nullable=True, comment="外部系统唯一编号"))
    op.add_column(
        "leads",
        sa.Column(
            "attribution_status",
            sa.String(20),
            nullable=False,
            server_default="matched",
            comment="场次归属状态：matched/pending",
        ),
    )
    op.create_index(
        "uq_leads_external_source_id",
        "leads",
        ["external_source", "external_id"],
        unique=True,
    )
    op.create_index(
        "idx_leads_attribution_time",
        "leads",
        ["attribution_status", "create_time"],
        unique=False,
    )

    op.create_table(
        "lead_sync_states",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, comment="ID"),
        sa.Column("source_system", sa.String(50), nullable=False, unique=True, comment="外部客资系统标识"),
        sa.Column("last_external_id", sa.BigInteger(), nullable=False, server_default="0", comment="已成功保存的最大外部编号"),
        sa.Column("status", sa.String(20), nullable=False, server_default="idle", comment="idle/running/completed/failed"),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True, comment="最近成功同步时间"),
        sa.Column("last_error", sa.Text(), nullable=True, comment="最近一次失败原因，不包含客资隐私"),
        sa.Column("synced_count", sa.Integer(), nullable=False, server_default="0", comment="累计新增客资数"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0", comment="累计跳过重复数"),
        sa.Column("pending_count", sa.Integer(), nullable=False, server_default="0", comment="待人工归属场次数"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), comment="更新时间"),
    )


def downgrade() -> None:
    """仅供开发环境回退；生产不会自动执行删除数据的回退。"""
    # 旧代码无法读取 session_id 为空的客资。回滚前先明确阻断并提示人工处理，
    # 不能删除真实客资，也不能为了通过约束伪造场次。检查必须放在所有 DDL
    # （改表语句）之前，因为 MySQL 改表会自动提交，晚检查会留下半回滚状态。
    pending_count = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM leads WHERE session_id IS NULL")
    ).scalar_one()
    if pending_count:
        raise RuntimeError(
            f"检测到 {pending_count} 条待归属客资，无法安全回滚；"
            "请先完成场次归属或导出备份"
        )
    op.drop_table("lead_sync_states")
    op.drop_index("idx_leads_attribution_time", table_name="leads")
    op.drop_index("uq_leads_external_source_id", table_name="leads")
    op.drop_column("leads", "attribution_status")
    op.drop_column("leads", "external_id")
    op.drop_column("leads", "external_source")
    op.drop_column("leads", "anchor_name")
    op.drop_column("leads", "douyin_id")
    op.alter_column(
        "leads",
        "session_id",
        existing_type=sa.Integer(),
        nullable=False,
        existing_comment="真实匹配的直播场次ID",
        comment="关联直播场次ID",
    )
