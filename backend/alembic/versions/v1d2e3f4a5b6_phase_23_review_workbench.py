"""Review workbench, action loop, script assets and compliance rules.

Revision ID: v1d2e3f4a5b6
Revises: u1d2e3f4a5b6
"""

from alembic import op
import sqlalchemy as sa


revision = "v1d2e3f4a5b6"
down_revision = "u1d2e3f4a5b6"
branch_labels = None
depends_on = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    default = sa.text("CURRENT_TIMESTAMP")
    return (
        sa.Column("created_at", sa.DateTime(), server_default=default, nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), server_default=default, nullable=False, comment="更新时间"),
    )


def upgrade() -> None:
    created_at, updated_at = _timestamps()
    op.create_table(
        "review_findings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="复盘发现ID"),
        sa.Column("session_id", sa.Integer(), nullable=False, comment="关联直播场次ID"),
        sa.Column("report_id", sa.Integer(), nullable=True, comment="关联AI报告ID"),
        sa.Column("evidence_key", sa.String(160), nullable=False, comment="真实证据幂等键"),
        sa.Column("finding_type", sa.String(30), server_default="observation", nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(20), server_default="info", nullable=False),
        sa.Column("start_seconds", sa.DECIMAL(12, 1), nullable=True),
        sa.Column("end_seconds", sa.DECIMAL(12, 1), nullable=True),
        sa.Column("evidence_type", sa.String(30), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("metric_name", sa.String(60), nullable=True),
        sa.Column("metric_before", sa.DECIMAL(14, 4), nullable=True),
        sa.Column("metric_after", sa.DECIMAL(14, 4), nullable=True),
        sa.Column("confidence", sa.DECIMAL(5, 4), server_default="1", nullable=False),
        sa.Column("source", sa.String(30), server_default="rule", nullable=False),
        sa.Column("status", sa.String(20), server_default="open", nullable=False),
        created_at,
        updated_at,
        sa.ForeignKeyConstraint(["session_id"], ["live_sessions.id"]),
        sa.ForeignKeyConstraint(["report_id"], ["analysis_reports.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "evidence_key", name="uq_review_finding_session_evidence"),
    )
    op.create_index("idx_review_finding_session_status", "review_findings", ["session_id", "status", "severity"])
    op.create_index("idx_review_finding_session_seconds", "review_findings", ["session_id", "start_seconds"])

    created_at, updated_at = _timestamps()
    op.create_table(
        "review_action_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="整改任务ID"),
        sa.Column("session_id", sa.Integer(), nullable=False, comment="来源直播场次ID"),
        sa.Column("finding_id", sa.BigInteger(), nullable=True, comment="来源复盘发现ID"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_name", sa.String(100), nullable=True),
        sa.Column("priority", sa.String(20), server_default="medium", nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("verification_session_id", sa.Integer(), nullable=True),
        sa.Column("verification_note", sa.Text(), nullable=True),
        created_at,
        updated_at,
        sa.ForeignKeyConstraint(["session_id"], ["live_sessions.id"]),
        sa.ForeignKeyConstraint(["finding_id"], ["review_findings.id"]),
        sa.ForeignKeyConstraint(["verification_session_id"], ["live_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_review_action_session_status", "review_action_items", ["session_id", "status", "priority"])

    created_at, updated_at = _timestamps()
    op.create_table(
        "script_assets",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="话术资产ID"),
        sa.Column("session_id", sa.Integer(), nullable=False, comment="来源直播场次ID"),
        sa.Column("transcript_segment_id", sa.BigInteger(), nullable=True, comment="来源真实话术片段ID"),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("start_seconds", sa.DECIMAL(12, 1), nullable=True),
        sa.Column("end_seconds", sa.DECIMAL(12, 1), nullable=True),
        sa.Column("performance_note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), server_default="candidate", nullable=False),
        created_at,
        updated_at,
        sa.ForeignKeyConstraint(["session_id"], ["live_sessions.id"]),
        sa.ForeignKeyConstraint(["transcript_segment_id"], ["transcript_segments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "transcript_segment_id", name="uq_script_asset_segment"),
    )
    op.create_index("idx_script_asset_category_status", "script_assets", ["category", "status"])

    created_at, updated_at = _timestamps()
    op.create_table(
        "compliance_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="合规规则ID"),
        sa.Column("rule_code", sa.String(60), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(20), server_default="warning", nullable=False),
        sa.Column("guidance", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("enabled", sa.Integer(), server_default="1", nullable=False),
        created_at,
        updated_at,
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_code", "version", name="uq_compliance_rule_code_version"),
    )
    op.create_index("idx_compliance_rule_enabled_category", "compliance_rules", ["enabled", "category"])

    rules = sa.table(
        "compliance_rules",
        sa.column("rule_code", sa.String),
        sa.column("name", sa.String),
        sa.column("category", sa.String),
        sa.column("pattern", sa.Text),
        sa.column("severity", sa.String),
        sa.column("guidance", sa.Text),
        sa.column("source_url", sa.String),
        sa.column("version", sa.Integer),
        sa.column("enabled", sa.Integer),
    )
    food_rule = "https://school.jinritemai.com/doudian/wap/article/aJkzdMC7vUSV"
    lead_rule = "https://open.douyin.com/platform/resource/docs/ability/enterprise-account-open-ability/enterprise-user-solution/"
    op.bulk_insert(
        rules,
        [
            {
                "rule_code": "food-effect-claim",
                "name": "食品功效或效果承诺待核验",
                "category": "食品宣传",
                "pattern": "治疗|治愈|降血压|降血糖|减肥必瘦|增强免疫力|改善疾病",
                "severity": "critical",
                "guidance": "不要把普通食品描述为具有疾病治疗或确定性保健效果；保留完整上下文并交由合规人员复核。",
                "source_url": food_rule,
                "version": 1,
                "enabled": 1,
            },
            {
                "rule_code": "absolute-or-profit-claim",
                "name": "绝对化或经营收益承诺待核验",
                "category": "经营承诺",
                "pattern": "稳赚不赔|保证赚钱|百分百赚钱|零风险|一定回本|绝对不会亏|全网第一|最低价",
                "severity": "critical",
                "guidance": "改成基于真实样本和条件的经验说明，明确选址、租金、面积、供应链等变量，不承诺收益结果。",
                "source_url": food_rule,
                "version": 1,
                "enabled": 1,
            },
            {
                "rule_code": "qualification-claim",
                "name": "资质、授权或来源宣称待核验",
                "category": "资质证明",
                "pattern": "官方认证|官方授权|独家授权|专利产品|有机食品|进口原装|原产地直供|自家生产",
                "severity": "warning",
                "guidance": "只有在直播画面、商品详情或内部资料中具备可核验凭证时才能使用相应表述。",
                "source_url": food_rule,
                "version": 1,
                "enabled": 1,
            },
            {
                "rule_code": "off-platform-diversion",
                "name": "站外联系方式或导流待核验",
                "category": "站外导流",
                "pattern": "加微信|加V|加微|微信号|扫二维码|手机号发我|去其他平台",
                "severity": "critical",
                "guidance": "优先引导用户在抖音站内主动私信或使用经授权的企业号留资组件，不在直播间公开收集联系方式。",
                "source_url": lead_rule,
                "version": 1,
                "enabled": 1,
            },
            {
                "rule_code": "scarcity-or-fake-case",
                "name": "虚构稀缺性或案例结果待核验",
                "category": "经营承诺",
                "pattern": "仅剩最后|最后几个名额|今天不领就没了|已经帮几百人赚钱|成功率百分百",
                "severity": "warning",
                "guidance": "资料领取条件、数量和案例效果必须真实；科普直播应以信息价值和用户主动咨询作为转化路径。",
                "source_url": food_rule,
                "version": 1,
                "enabled": 1,
            },
        ],
    )


def downgrade() -> None:
    op.drop_index("idx_compliance_rule_enabled_category", table_name="compliance_rules")
    op.drop_table("compliance_rules")
    op.drop_index("idx_script_asset_category_status", table_name="script_assets")
    op.drop_table("script_assets")
    op.drop_index("idx_review_action_session_status", table_name="review_action_items")
    op.drop_table("review_action_items")
    op.drop_index("idx_review_finding_session_seconds", table_name="review_findings")
    op.drop_index("idx_review_finding_session_status", table_name="review_findings")
    op.drop_table("review_findings")
