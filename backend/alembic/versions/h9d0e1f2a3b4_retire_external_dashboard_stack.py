"""彻底退役 DataEase 数据表、语义视图和后台状态。

Revision ID: h9d0e1f2a3b4
Revises: g8c9d0e1f2a3
Create Date: 2026-08-30

这次迁移按产品决策删除 DataEase 派生数据。直播场次、评论、分钟指标、话术、
AI 复盘和知识库等真实业务源表不受影响；原生经营大屏直接查询这些源表。
"""

from alembic import op
from sqlalchemy.exc import OperationalError
from sqlalchemy.dialects import mysql


revision = "h9d0e1f2a3b4"
down_revision = "g8c9d0e1f2a3"
branch_labels = None
depends_on = None


DATAEASE_VIEWS = (
    "de_v_fact_ai_call_trace",
    "de_v_fact_anchor_schedule",
    "de_v_fact_script_asset",
    "de_v_fact_review_action",
    "de_v_fact_review_finding",
    "de_v_fact_ai_analysis",
    "de_v_fact_transcript_segment",
    "de_v_fact_comment",
    "de_v_fact_live_minute_metric",
    "de_v_fact_live_session",
    "de_v_dim_date",
    "de_v_dim_anchor",
)

DATAEASE_TABLES = (
    "de_anchor_ai_analysis_summary",
    "de_anchor_transcript_summary",
    "de_anchor_comment_summary",
    "de_anchor_audience_profile",
    "de_anchor_conversion_funnel",
    "de_anchor_realtime_metrics",
    "de_live_session_anchor_summary",
)


def _drop_legacy_view(view_name: str) -> None:
    """删除历史高权限账号创建的视图，并给旧部署明确的升级指引。"""
    try:
        op.execute(f"DROP VIEW IF EXISTS `{view_name}`")
    except OperationalError as exc:
        error_code = exc.orig.args[0] if getattr(exc, "orig", None) else None
        if error_code == 1227:
            raise RuntimeError(
                "历史视图由 MySQL 高权限账号创建；请仅为本次迁移临时执行 "
                "`DB_USER=root DB_PASSWORD=<MYSQL_ROOT_PASSWORD> .venv/bin/alembic upgrade head`，"
                "迁移完成后继续使用普通应用账号"
            ) from exc
        raise


def upgrade() -> None:
    # 先停止并清理自动同步模块状态，避免旧任务在迁移期间继续访问待删表。
    op.execute(
        "UPDATE scraper_tasks "
        "SET status = 'cancelled', progress_stage = 'retired', "
        "progress_message = 'DataEase 已退役，历史任务不再执行', "
        "completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP) "
        "WHERE task_type = 'dataease_sync' "
        "AND status IN ('pending', 'queued', 'running', 'processing')"
    )
    op.execute("DELETE FROM collector_module_states WHERE module_key = 'dataease'")

    # 视图依赖业务表，必须先删视图再删派生宽表。
    for view_name in DATAEASE_VIEWS:
        _drop_legacy_view(view_name)
    for table_name in DATAEASE_TABLES:
        op.execute(f"DROP TABLE IF EXISTS `{table_name}`")

    # 同步清理仍会出现在数据库管理工具中的历史模块说明，不改变字段数据。
    op.alter_column(
        "asr_tasks",
        "postprocess_result",
        existing_type=mysql.JSON(),
        existing_nullable=True,
        comment="话术、复盘和知识库处理结果",
    )


def downgrade() -> None:
    # 本迁移对应用户明确确认的永久退役。降级无法恢复已删除的派生数据，必须从
    # 迁移前数据库备份恢复，避免创建一组看似存在、实际内容为空的误导性表。
    raise RuntimeError("DataEase 退役迁移不可直接降级，请从迁移前数据库备份恢复")
