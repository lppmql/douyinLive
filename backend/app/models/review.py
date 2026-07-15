"""直播复盘工作台领域模型。"""

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    DECIMAL,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.models.base import Base, TimestampMixin


class ReviewFinding(Base, TimestampMixin):
    """基于真实话术、评论和指标生成的可追溯复盘发现。"""

    __tablename__ = "review_findings"
    __table_args__ = (
        UniqueConstraint("session_id", "evidence_key", name="uq_review_finding_session_evidence"),
        Index("idx_review_finding_session_status", "session_id", "status", "severity"),
        Index("idx_review_finding_session_seconds", "session_id", "start_seconds"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="复盘发现ID")
    session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=False, comment="关联直播场次ID")
    report_id = Column(Integer, ForeignKey("analysis_reports.id"), nullable=True, comment="关联AI报告ID")
    evidence_key = Column(String(160), nullable=False, comment="真实证据幂等键")
    finding_type = Column(String(30), nullable=False, default="observation", comment="observation/opportunity/risk")
    category = Column(String(40), nullable=False, comment="留人/互动/资料钩子/私信留资/内容/合规/数据质量")
    title = Column(String(200), nullable=False, comment="发现标题")
    description = Column(Text, nullable=True, comment="发现说明")
    severity = Column(String(20), nullable=False, default="info", comment="info/warning/critical")
    start_seconds = Column(DECIMAL(12, 1), nullable=True, comment="证据相对开播开始秒数")
    end_seconds = Column(DECIMAL(12, 1), nullable=True, comment="证据相对开播结束秒数")
    evidence_type = Column(String(30), nullable=False, comment="metric/comment/transcript/session")
    evidence_text = Column(Text, nullable=True, comment="真实证据原文或指标变化")
    metric_name = Column(String(60), nullable=True, comment="关联指标名")
    metric_before = Column(DECIMAL(14, 4), nullable=True, comment="变化前指标")
    metric_after = Column(DECIMAL(14, 4), nullable=True, comment="变化后指标")
    confidence = Column(DECIMAL(5, 4), nullable=False, default=1, comment="判断置信度0-1")
    source = Column(String(30), nullable=False, default="rule", comment="rule/ai/manual")
    status = Column(String(20), nullable=False, default="open", comment="open/confirmed/dismissed/resolved")


class ReviewActionItem(Base, TimestampMixin):
    """将复盘发现转成可跟踪、可验证的整改任务。"""

    __tablename__ = "review_action_items"
    __table_args__ = (
        Index("idx_review_action_session_status", "session_id", "status", "priority"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="整改任务ID")
    session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=False, comment="来源直播场次ID")
    finding_id = Column(BigInteger, ForeignKey("review_findings.id"), nullable=True, comment="来源复盘发现ID")
    title = Column(String(200), nullable=False, comment="整改标题")
    description = Column(Text, nullable=True, comment="整改要求")
    owner_name = Column(String(100), nullable=True, comment="负责人")
    priority = Column(String(20), nullable=False, default="medium", comment="low/medium/high")
    status = Column(String(20), nullable=False, default="pending", comment="pending/in_progress/completed/verified")
    due_at = Column(DateTime, nullable=True, comment="计划完成时间")
    verification_session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=True, comment="验证场次ID")
    verification_note = Column(Text, nullable=True, comment="验证结论")


class ScriptAsset(Base, TimestampMixin):
    """从真实直播片段沉淀的零食店知识科普话术资产。"""

    __tablename__ = "script_assets"
    __table_args__ = (
        UniqueConstraint("session_id", "transcript_segment_id", name="uq_script_asset_segment"),
        Index("idx_script_asset_category_status", "category", "status"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="话术资产ID")
    session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=False, comment="来源直播场次ID")
    transcript_segment_id = Column(
        BigInteger,
        ForeignKey("transcript_segments.id"),
        nullable=True,
        comment="来源真实话术片段ID",
    )
    category = Column(String(40), nullable=False, comment="开场留人/选址/预算/品牌/供应链/毛利/损耗/资料钩子/私信承接")
    title = Column(String(200), nullable=False, comment="话术标题")
    content = Column(Text, nullable=False, comment="真实话术原文")
    start_seconds = Column(DECIMAL(12, 1), nullable=True, comment="片段开始秒数")
    end_seconds = Column(DECIMAL(12, 1), nullable=True, comment="片段结束秒数")
    performance_note = Column(Text, nullable=True, comment="关联真实效果说明")
    status = Column(String(20), nullable=False, default="candidate", comment="candidate/approved/archived")


class ComplianceRule(Base, TimestampMixin):
    """可版本化的直播话术风险提示规则，不直接替代人工合规判断。"""

    __tablename__ = "compliance_rules"
    __table_args__ = (
        UniqueConstraint("rule_code", "version", name="uq_compliance_rule_code_version"),
        Index("idx_compliance_rule_enabled_category", "enabled", "category"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="合规规则ID")
    rule_code = Column(String(60), nullable=False, comment="稳定规则编码")
    name = Column(String(120), nullable=False, comment="规则名称")
    category = Column(String(40), nullable=False, comment="食品宣传/经营承诺/绝对化/站外导流/资质证明")
    pattern = Column(Text, nullable=False, comment="需要人工复核的关键词，使用竖线分隔")
    severity = Column(String(20), nullable=False, default="warning", comment="warning/critical")
    guidance = Column(Text, nullable=False, comment="合规改写或核验建议")
    source_url = Column(String(1000), nullable=True, comment="公开规则来源")
    version = Column(Integer, nullable=False, default=1, comment="规则版本")
    enabled = Column(Integer, nullable=False, default=1, comment="是否启用")
