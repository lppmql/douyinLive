"""
DataEase 大屏专用汇总宽表（7 张）

所有 de_ 表由同步服务（app/services/sync/）从业务表定时写入。
DataEase 通过 JDBC 数据源直连业务 MySQL，只读 de_ 表，不碰业务表。

字段规则：
- 比率字段 DECIMAL(10,4) 存小数，如 0.1427 = 14.27%
- 金额字段 DECIMAL(10,2)，计数 INT，时长 DECIMAL(10,1)
"""
from sqlalchemy import Column, Integer, String, DateTime, DECIMAL, BigInteger, Date, Index
from app.models.base import Base, TimestampMixin


class DeLiveSessionAnchorSummary(Base, TimestampMixin):
    """[DE] 直播场次主播汇总宽表 — 每场直播 1 条，DataEase 核心数据集"""

    __tablename__ = "de_live_session_anchor_summary"
    __table_args__ = (
        Index("idx_de_summary_stat_date", "stat_date"),
        Index("idx_de_summary_anchor", "anchor_name"),
        {"comment": "[DE] 直播场次主播汇总宽表 — 每场直播1条"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="ID")
    stat_date = Column(Date, nullable=True, comment="统计日期")
    session_id = Column(Integer, nullable=False, unique=True, comment="关联直播场次ID")
    room_id = Column(Integer, nullable=True, comment="关联直播间ID")

    # 主播信息
    anchor_name = Column(String(100), nullable=True, comment="主播名称")
    team_name = Column(String(100), nullable=True, comment="所属团队")

    # 时间/时长
    session_title = Column(String(200), nullable=True, comment="直播标题")
    live_start_time = Column(DateTime, nullable=True, comment="开播时间")
    live_end_time = Column(DateTime, nullable=True, comment="下播时间")
    live_duration_seconds = Column(Integer, default=0, comment="直播时长（秒）")

    # 核心指标
    total_viewers = Column(Integer, default=0, comment="累计观看人数")
    avg_watch_seconds = Column(DECIMAL(10, 1), default=0, comment="人均观看时长（秒）")
    peak_online_count = Column(Integer, default=0, comment="最高在线人数")
    realtime_online_count = Column(Integer, default=0, comment="实时在线人数")
    ad_cost = Column(DECIMAL(10, 2), default=0, comment="广告消耗（元）")
    new_followers = Column(Integer, default=0, comment="涨粉量")
    comments_count = Column(Integer, default=0, comment="评论总数")
    leads_count = Column(Integer, default=0, comment="留资总数（含无效）")
    valid_leads_count = Column(Integer, default=0, comment="有效留资数")
    lead_valid_rate = Column(DECIMAL(10, 4), default=0, comment="有效留资率")
    lead_cost = Column(DECIMAL(10, 2), default=0, comment="线索成本（元/条）")

    # 比率指标
    exposure_enter_rate = Column(DECIMAL(10, 4), default=0, comment="曝光进入率")
    share_rate = Column(DECIMAL(10, 4), default=0, comment="分享率")
    like_rate = Column(DECIMAL(10, 4), default=0, comment="点赞率")
    comment_rate = Column(DECIMAL(10, 4), default=0, comment="评论率")
    interaction_rate = Column(DECIMAL(10, 4), default=0, comment="互动率")

    # 流量来源占比
    natural_traffic_ratio = Column(DECIMAL(10, 4), default=0, comment="自然流量占比")
    marketing_traffic_ratio = Column(DECIMAL(10, 4), default=0, comment="营销流量占比")
    other_traffic_ratio = Column(DECIMAL(10, 4), default=0, comment="其他流量占比")

    # 转化漏斗
    live_exposure_users = Column(Integer, default=0, comment="直播间曝光人数")
    live_enter_users = Column(Integer, default=0, comment="直播进入人数")
    card_click_users = Column(Integer, default=0, comment="小风车/讲解卡点击人数")
    private_message_count = Column(Integer, default=0, comment="私信人数")
    scene_leads_count = Column(Integer, default=0, comment="全场景线索人数")
    mini_windmill_click_count = Column(Integer, default=0, comment="小风车点击次数")


class DeAnchorRealtimeMetrics(Base, TimestampMixin):
    """[DE] 分钟级实时指标 — 每场直播每分钟 1 条"""

    __tablename__ = "de_anchor_realtime_metrics"
    __table_args__ = (
        Index("idx_de_metrics_session_time", "session_id", "metric_time"),
        {"comment": "[DE] 分钟级实时指标 — 每场直播每分钟1条"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="ID")
    session_id = Column(Integer, nullable=False, comment="关联直播场次ID")
    anchor_name = Column(String(100), nullable=True, comment="主播名称")
    session_title = Column(String(200), nullable=True, comment="直播标题")
    metric_time = Column(DateTime, nullable=False, comment="指标时间（分钟级）")

    # 流量
    avg_online_count = Column(DECIMAL(10, 1), default=0, comment="平均在线人数")
    max_online_count = Column(Integer, default=0, comment="最大在线人数")
    avg_exposure_count = Column(DECIMAL(10, 1), default=0, comment="平均曝光次数")
    avg_enter_count = Column(DECIMAL(10, 1), default=0, comment="平均进入人数")

    # 互动
    total_like_count = Column(Integer, default=0, comment="累计点赞量")
    total_comment_count = Column(Integer, default=0, comment="累计评论量")
    total_follow_count = Column(Integer, default=0, comment="累计关注量")

    # 流量来源
    avg_natural_traffic = Column(DECIMAL(10, 1), default=0, comment="平均自然流量")
    avg_marketing_traffic = Column(DECIMAL(10, 1), default=0, comment="平均营销流量")

    # 元数据
    metric_count = Column(Integer, default=0, comment="聚合的原始记录数")


class DeAnchorConversionFunnel(Base, TimestampMixin):
    """[DE] 转化漏斗 — 每场 5 步：曝光→进入→点击→私信→留资"""

    __tablename__ = "de_anchor_conversion_funnel"
    __table_args__ = (
        Index("idx_de_funnel_session", "session_id"),
        {"comment": "[DE] 转化漏斗 — 每场5步：曝光→进入→点击→私信→留资"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="ID")
    session_id = Column(Integer, nullable=False, comment="关联直播场次ID")
    anchor_name = Column(String(100), nullable=True, comment="主播名称")
    session_title = Column(String(200), nullable=True, comment="直播标题")
    stat_date = Column(Date, nullable=True, comment="统计日期")
    funnel_step = Column(String(20), nullable=False, comment="漏斗步骤")
    user_count = Column(Integer, default=0, comment="本步用户数")
    prev_step_user_count = Column(Integer, default=0, comment="上一步用户数")
    step_rate = Column(DECIMAL(10, 4), default=0, comment="本步转化率")


class DeAnchorAudienceProfile(Base, TimestampMixin):
    """[DE] 用户画像 — 年龄/性别/地域分布"""

    __tablename__ = "de_anchor_audience_profile"
    __table_args__ = (
        Index("idx_de_profile_session", "session_id"),
        {"comment": "[DE] 用户画像 — 年龄/性别/地域分布"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="ID")
    session_id = Column(Integer, nullable=False, comment="关联直播场次ID")
    anchor_name = Column(String(100), nullable=True, comment="主播名称")
    session_title = Column(String(200), nullable=True, comment="直播标题")
    dimension_type = Column(String(20), nullable=False, comment="维度类型")
    dimension_name = Column(String(50), nullable=False, comment="维度名称")
    ratio = Column(DECIMAL(10, 4), default=0, comment="占比")
    count = Column(Integer, default=0, comment="人数")


class DeAnchorCommentSummary(Base, TimestampMixin):
    """[DE] 评论汇总 — 每场直播 1 条"""

    __tablename__ = "de_anchor_comment_summary"
    __table_args__ = {"comment": "[DE] 评论汇总 — 每场直播1条"}

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="ID")
    session_id = Column(Integer, nullable=False, unique=True, comment="关联直播场次ID")
    anchor_name = Column(String(100), nullable=True, comment="主播名称")
    session_title = Column(String(200), nullable=True, comment="直播标题")
    stat_date = Column(Date, nullable=True, comment="统计日期")
    total_comments = Column(Integer, default=0, comment="总评论数")
    high_intent_count = Column(Integer, default=0, comment="高意向评论数")
    positive_count = Column(Integer, default=0, comment="正面情绪评论数")
    neutral_count = Column(Integer, default=0, comment="中性情绪评论数")
    negative_count = Column(Integer, default=0, comment="负面情绪评论数")


class DeAnchorTranscriptSummary(Base, TimestampMixin):
    """[DE] 话术汇总 — 每场直播 1 条"""

    __tablename__ = "de_anchor_transcript_summary"
    __table_args__ = {"comment": "[DE] 话术汇总 — 每场直播1条"}

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="ID")
    session_id = Column(Integer, nullable=False, unique=True, comment="关联直播场次ID")
    anchor_name = Column(String(100), nullable=True, comment="主播名称")
    session_title = Column(String(200), nullable=True, comment="直播标题")
    total_segments = Column(Integer, default=0, comment="话术分段数")
    total_text_length = Column(Integer, default=0, comment="完整话术长度（字符数）")
    avg_ai_score = Column(DECIMAL(3, 1), nullable=True, comment="平均AI评分（0-10）")
    asr_status = Column(String(20), default="pending", comment="ASR状态")


class DeAnchorAiAnalysisSummary(Base, TimestampMixin):
    """[DE] AI 分析汇总 — 每场直播 1 条，Phase 7 填充数据"""

    __tablename__ = "de_anchor_ai_analysis_summary"
    __table_args__ = {"comment": "[DE] AI分析汇总 — 每场直播1条，Phase7填充数据"}

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="ID")
    session_id = Column(Integer, nullable=False, unique=True, comment="关联直播场次ID")
    anchor_name = Column(String(100), nullable=True, comment="主播名称")
    session_title = Column(String(200), nullable=True, comment="直播标题")
    ai_total_score = Column(DECIMAL(3, 1), nullable=True, comment="AI综合评分")
    completeness_score = Column(DECIMAL(3, 1), nullable=True, comment="完整性评分")
    interactivity_score = Column(DECIMAL(3, 1), nullable=True, comment="互动性评分")
    lead_guidance_score = Column(DECIMAL(3, 1), nullable=True, comment="留资引导评分")
    report_count = Column(Integer, default=0, comment="分析报告数量")
