"""Phase 32：采集控制中心、任务停止重试与日志上下文。

Revision ID: 3a7c1f9e2d44
Revises: 27d9dc5d2b31
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa


revision = "3a7c1f9e2d44"
down_revision = "27d9dc5d2b31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """只增加可空字段和索引，保证已有真实数据原样保留。"""
    op.add_column(
        "scraper_accounts",
        sa.Column("douyin_nickname", sa.String(length=100), nullable=True, comment="扫码抖音账号真实昵称"),
    )
    op.add_column(
        "scraper_accounts",
        sa.Column("cookie_checked_at", sa.DateTime(), nullable=True, comment="最近一次真实检查 Cookie 的时间"),
    )
    op.add_column(
        "scraper_accounts",
        sa.Column("cookie_refreshed_at", sa.DateTime(), nullable=True, comment="最近一次保存新 Cookie 的时间"),
    )

    op.add_column(
        "scraper_tasks",
        sa.Column("cancel_requested_at", sa.DateTime(), nullable=True, comment="用户请求安全停止任务的时间"),
    )
    op.add_column(
        "scraper_tasks",
        sa.Column("retry_of_task_id", sa.BigInteger(), nullable=True, comment="本次任务重试自哪个历史任务"),
    )
    op.add_column(
        "scraper_tasks",
        sa.Column("task_options_json", sa.JSON(), nullable=True, comment="任务启动参数快照"),
    )
    op.add_column(
        "scraper_tasks",
        sa.Column("result_json", sa.JSON(), nullable=True, comment="任务完成后的结构化结果"),
    )
    op.create_index("idx_scraper_tasks_retry_of", "scraper_tasks", ["retry_of_task_id"], unique=False)

    op.add_column(
        "asr_tasks",
        sa.Column("cancel_requested_at", sa.DateTime(), nullable=True, comment="用户请求安全停止转写的时间"),
    )

    op.add_column(
        "scraper_logs",
        sa.Column("session_id", sa.Integer(), nullable=True, comment="关联直播场次 ID 快照"),
    )
    op.add_column(
        "scraper_logs",
        sa.Column("anchor_name", sa.String(length=100), nullable=True, comment="关联主播名称快照"),
    )
    op.add_column(
        "scraper_logs",
        sa.Column("session_title", sa.String(length=255), nullable=True, comment="关联直播标题快照"),
    )
    op.add_column(
        "scraper_logs",
        sa.Column("room_id_str", sa.String(length=100), nullable=True, comment="平台直播房间 ID 快照"),
    )
    op.add_column(
        "scraper_logs",
        sa.Column("event_type", sa.String(length=50), nullable=True, comment="结构化日志事件类型"),
    )
    op.add_column(
        "scraper_logs",
        sa.Column("stage", sa.String(length=50), nullable=True, comment="任务执行阶段"),
    )
    op.create_index("idx_scraper_logs_session_id", "scraper_logs", ["session_id", "id"], unique=False)
    op.create_index("idx_scraper_logs_stage_id", "scraper_logs", ["stage", "id"], unique=False)


def downgrade() -> None:
    """回滚仅删除本次新增结构，不触碰原有业务字段。"""
    op.drop_index("idx_scraper_logs_stage_id", table_name="scraper_logs")
    op.drop_index("idx_scraper_logs_session_id", table_name="scraper_logs")
    op.drop_column("scraper_logs", "stage")
    op.drop_column("scraper_logs", "event_type")
    op.drop_column("scraper_logs", "room_id_str")
    op.drop_column("scraper_logs", "session_title")
    op.drop_column("scraper_logs", "anchor_name")
    op.drop_column("scraper_logs", "session_id")

    op.drop_column("asr_tasks", "cancel_requested_at")

    op.drop_index("idx_scraper_tasks_retry_of", table_name="scraper_tasks")
    op.drop_column("scraper_tasks", "result_json")
    op.drop_column("scraper_tasks", "task_options_json")
    op.drop_column("scraper_tasks", "retry_of_task_id")
    op.drop_column("scraper_tasks", "cancel_requested_at")

    op.drop_column("scraper_accounts", "cookie_refreshed_at")
    op.drop_column("scraper_accounts", "cookie_checked_at")
    op.drop_column("scraper_accounts", "douyin_nickname")
