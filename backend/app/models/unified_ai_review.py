"""统一 AI 复盘模型：同一份结果同时服务场次详情和 AI 复盘页。"""

from sqlalchemy import BigInteger, Column, DateTime, DECIMAL, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint

from app.models.base import Base, TimestampMixin


class UnifiedAiReviewRun(Base, TimestampMixin):
    """每个场次的最新统一 AI 复盘任务。"""

    __tablename__ = "unified_ai_review_runs"
    __table_args__ = (
        UniqueConstraint("session_id", name="uq_unified_ai_review_run_session"),
        Index("idx_unified_ai_review_status", "status", "updated_at"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="统一AI复盘任务ID")
    session_id = Column(Integer, ForeignKey("live_sessions.id", ondelete="CASCADE"), nullable=False, comment="直播场次ID")
    status = Column(String(20), nullable=False, default="pending", comment="pending/running/completed/failed/stale")
    input_hash = Column(String(64), nullable=False, default="", comment="真实输入数据指纹")
    analysis_version = Column(String(30), nullable=False, comment="分析规则与提示词版本")
    model_name = Column(String(100), nullable=True, comment="AI模型名称")
    summary = Column(JSON, nullable=False, default=dict, comment="整场结构化复盘汇总")
    analyzed_user_count = Column(Integer, nullable=False, default=0, comment="已分析用户数")
    error_message = Column(Text, nullable=True, comment="失败原因，不包含联系方式")
    completed_at = Column(DateTime, nullable=True, comment="最近完成时间")
    generation_token = Column(String(36), nullable=True, comment="跨进程生成任务租约令牌")
    lease_expires_at = Column(DateTime, nullable=True, comment="生成任务租约过期时间")


class AudienceInteractionAnalysis(Base, TimestampMixin):
    """按用户聚合的评论—主播回应—转化 AI 分析。"""

    __tablename__ = "audience_interaction_analyses"
    __table_args__ = (
        UniqueConstraint("session_id", "identity_key", name="uq_audience_interaction_session_user"),
        Index("idx_audience_interaction_precision", "session_id", "is_precision_lead", "interaction_type"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="用户互动分析ID")
    run_id = Column(BigInteger, ForeignKey("unified_ai_review_runs.id", ondelete="CASCADE"), nullable=False, comment="所属统一复盘任务")
    session_id = Column(Integer, ForeignKey("live_sessions.id", ondelete="CASCADE"), nullable=False, comment="直播场次ID")
    identity_key = Column(String(255), nullable=False, comment="评论用户稳定标识")
    user_nickname = Column(String(200), nullable=True, comment="用于复盘页展示的真实评论昵称")
    business_stage = Column(String(30), nullable=False, default="unknown", comment="准备开店/已开店/疑似已交钱/unknown")
    follow_up_status = Column(String(30), nullable=False, default="unknown", comment="未留资/已留资/疑似联系过拓展/unknown")
    demand_scope = Column(String(30), nullable=False, default="unknown", comment="零食店/非零食店/同行/unknown")
    interaction_type = Column(String(30), nullable=False, default="information_insufficient", comment="正常咨询/理性质疑/恶意攻击等")
    precision_status = Column(String(40), nullable=False, default="information_insufficient", comment="精准新客/存量用户/非目标等")
    is_precision_lead = Column(Integer, nullable=False, default=0, comment="是否精准新客")
    exclusion_reason = Column(Text, nullable=True, comment="不计精准新客的证据化原因")
    host_response_status = Column(String(30), nullable=False, default="unknown", comment="优秀承接/有效回应/答非所问/未回应")
    host_response_score = Column(Integer, nullable=True, comment="主播回应质量0-100")
    missed_opportunity = Column(Integer, nullable=False, default=0, comment="是否错失转化机会")
    recommendation = Column(Text, nullable=False, comment="针对该用户的改进建议")
    suggested_reply = Column(Text, nullable=True, comment="主播可直接使用的建议回答")
    confidence = Column(DECIMAL(5, 4), nullable=False, default=0, comment="AI判断置信度0-1")
    evidence = Column(JSON, nullable=False, default=list, comment="评论与主播原话证据")
    manual_override = Column(JSON, nullable=True, comment="人工确认结果，优先于AI")
