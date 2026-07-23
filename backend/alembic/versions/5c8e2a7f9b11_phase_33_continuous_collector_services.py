"""Phase 33：数据采集模块持久状态。

Revision ID: 5c8e2a7f9b11
Revises: 3a7c1f9e2d44
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa


revision = "5c8e2a7f9b11"
down_revision = "3a7c1f9e2d44"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """新增独立状态表，不改动任何已有主播、场次和采集数据。"""
    op.create_table(
        "collector_module_states",
        sa.Column("module_key", sa.String(length=32), nullable=False, comment="模块唯一标识"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false(), comment="是否长期运行"),
        sa.Column("interval_seconds", sa.Integer(), nullable=False, server_default="60", comment="增量检查间隔秒数"),
        sa.Column("enabled_at", sa.DateTime(), nullable=True, comment="最近开启时间"),
        sa.Column("disabled_at", sa.DateTime(), nullable=True, comment="最近彻底关闭时间"),
        sa.Column("last_scheduled_at", sa.DateTime(), nullable=True, comment="最近创建增量任务时间"),
        sa.Column("next_run_at", sa.DateTime(), nullable=True, comment="下一次增量检查时间"),
        sa.Column("last_task_id", sa.BigInteger(), nullable=True, comment="最近一次关联任务 ID"),
        sa.Column("last_error", sa.String(length=500), nullable=True, comment="最近一次调度错误或资源保护原因"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="创建时间"),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            server_onupdate=sa.text("CURRENT_TIMESTAMP"),
            comment="更新时间",
        ),
        sa.PrimaryKeyConstraint("module_key"),
    )
    op.create_index(
        "idx_collector_module_enabled_next",
        "collector_module_states",
        ["enabled", "next_run_at"],
        unique=False,
    )


def downgrade() -> None:
    """仅删除本次新增的开关状态，不触碰业务数据。"""
    op.drop_index("idx_collector_module_enabled_next", table_name="collector_module_states")
    op.drop_table("collector_module_states")
