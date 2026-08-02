"""Phase 41：统一AI复盘与用户互动分析。

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "g7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "unified_ai_review_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="统一AI复盘任务ID"),
        sa.Column("session_id", sa.Integer(), nullable=False, comment="直播场次ID"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending", comment="pending/running/completed/failed/stale"),
        sa.Column("input_hash", sa.String(64), nullable=False, server_default="", comment="真实输入数据指纹"),
        sa.Column("analysis_version", sa.String(30), nullable=False, comment="分析规则与提示词版本"),
        sa.Column("model_name", sa.String(100), nullable=True, comment="AI模型名称"),
        sa.Column("summary", sa.JSON(), nullable=False, comment="整场结构化复盘汇总"),
        sa.Column("analyzed_user_count", sa.Integer(), nullable=False, server_default="0", comment="已分析用户数"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="失败原因，不包含联系方式"),
        sa.Column("completed_at", sa.DateTime(), nullable=True, comment="最近完成时间"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), comment="更新时间"),
        sa.ForeignKeyConstraint(["session_id"], ["live_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_unified_ai_review_run_session"),
    )
    op.create_index("idx_unified_ai_review_status", "unified_ai_review_runs", ["status", "updated_at"])
    op.create_table(
        "audience_interaction_analyses",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="用户互动分析ID"),
        sa.Column("run_id", sa.BigInteger(), nullable=False, comment="所属统一复盘任务"),
        sa.Column("session_id", sa.Integer(), nullable=False, comment="直播场次ID"),
        sa.Column("identity_key", sa.String(255), nullable=False, comment="评论用户稳定标识"),
        sa.Column("user_nickname", sa.String(200), nullable=True, comment="用于复盘页展示的真实评论昵称"),
        sa.Column("business_stage", sa.String(30), nullable=False, server_default="unknown", comment="准备开店/已开店/疑似已交钱/unknown"),
        sa.Column("follow_up_status", sa.String(30), nullable=False, server_default="unknown", comment="未留资/已留资/疑似联系过拓展/unknown"),
        sa.Column("demand_scope", sa.String(30), nullable=False, server_default="unknown", comment="零食店/非零食店/同行/unknown"),
        sa.Column("interaction_type", sa.String(30), nullable=False, server_default="information_insufficient", comment="正常咨询/理性质疑/恶意攻击等"),
        sa.Column("precision_status", sa.String(40), nullable=False, server_default="information_insufficient", comment="精准新客/存量用户/非目标等"),
        sa.Column("is_precision_lead", sa.Integer(), nullable=False, server_default="0", comment="是否精准新客"),
        sa.Column("exclusion_reason", sa.Text(), nullable=True, comment="不计精准新客的证据化原因"),
        sa.Column("host_response_status", sa.String(30), nullable=False, server_default="unknown", comment="优秀承接/有效回应/答非所问/未回应"),
        sa.Column("host_response_score", sa.Integer(), nullable=True, comment="主播回应质量0-100"),
        sa.Column("missed_opportunity", sa.Integer(), nullable=False, server_default="0", comment="是否错失转化机会"),
        sa.Column("recommendation", sa.Text(), nullable=False, comment="针对该用户的改进建议"),
        sa.Column("suggested_reply", sa.Text(), nullable=True, comment="主播可直接使用的建议回答"),
        sa.Column("confidence", sa.DECIMAL(5, 4), nullable=False, server_default="0", comment="AI判断置信度0-1"),
        sa.Column("evidence", sa.JSON(), nullable=False, comment="评论与主播原话证据"),
        sa.Column("manual_override", sa.JSON(), nullable=True, comment="人工确认结果，优先于AI"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), comment="更新时间"),
        sa.ForeignKeyConstraint(["run_id"], ["unified_ai_review_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["live_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "identity_key", name="uq_audience_interaction_session_user"),
    )
    op.create_index("idx_audience_interaction_precision", "audience_interaction_analyses", ["session_id", "is_precision_lead", "interaction_type"])


def downgrade() -> None:
    op.drop_index("idx_audience_interaction_precision", table_name="audience_interaction_analyses")
    op.drop_table("audience_interaction_analyses")
    op.drop_index("idx_unified_ai_review_status", table_name="unified_ai_review_runs")
    op.drop_table("unified_ai_review_runs")
