"""Phase 6: 创建 7 张 DataEase 大屏汇总宽表

Revision ID: d1d2e3f4a5b6
Revises: c1d2e3f4a5b6
Create Date: 2026-07-10 06:30:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "d1d2e3f4a5b6"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### de_live_session_anchor_summary — 直播场次主播汇总宽表
    op.create_table(
        "de_live_session_anchor_summary",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="ID"),
        sa.Column("stat_date", sa.Date(), nullable=True, comment="统计日期"),
        sa.Column("session_id", sa.Integer(), nullable=False, comment="关联直播场次ID"),
        sa.Column("room_id", sa.Integer(), nullable=True, comment="关联直播间ID"),
        sa.Column("anchor_name", sa.String(100), nullable=True, comment="主播名称"),
        sa.Column("team_name", sa.String(100), nullable=True, comment="所属团队"),
        sa.Column("session_title", sa.String(200), nullable=True, comment="直播标题"),
        sa.Column("live_start_time", sa.DateTime(), nullable=True, comment="开播时间"),
        sa.Column("live_end_time", sa.DateTime(), nullable=True, comment="下播时间"),
        sa.Column("live_duration_seconds", sa.Integer(), default=0, comment="直播时长（秒）"),
        sa.Column("total_viewers", sa.Integer(), default=0, comment="累计观看人数"),
        sa.Column("avg_watch_seconds", sa.DECIMAL(10, 1), default=0, comment="人均观看时长（秒）"),
        sa.Column("peak_online_count", sa.Integer(), default=0, comment="最高在线人数"),
        sa.Column("realtime_online_count", sa.Integer(), default=0, comment="实时在线人数"),
        sa.Column("ad_cost", sa.DECIMAL(10, 2), default=0, comment="广告消耗（元）"),
        sa.Column("new_followers", sa.Integer(), default=0, comment="涨粉量"),
        sa.Column("comments_count", sa.Integer(), default=0, comment="评论总数"),
        sa.Column("leads_count", sa.Integer(), default=0, comment="留资总数（含无效）"),
        sa.Column("valid_leads_count", sa.Integer(), default=0, comment="有效留资数"),
        sa.Column("lead_valid_rate", sa.DECIMAL(10, 4), default=0, comment="有效留资率"),
        sa.Column("lead_cost", sa.DECIMAL(10, 2), default=0, comment="线索成本（元/条）"),
        sa.Column("exposure_enter_rate", sa.DECIMAL(10, 4), default=0, comment="曝光进入率"),
        sa.Column("share_rate", sa.DECIMAL(10, 4), default=0, comment="分享率"),
        sa.Column("like_rate", sa.DECIMAL(10, 4), default=0, comment="点赞率"),
        sa.Column("comment_rate", sa.DECIMAL(10, 4), default=0, comment="评论率"),
        sa.Column("interaction_rate", sa.DECIMAL(10, 4), default=0, comment="互动率"),
        sa.Column("natural_traffic_ratio", sa.DECIMAL(10, 4), default=0, comment="自然流量占比"),
        sa.Column("marketing_traffic_ratio", sa.DECIMAL(10, 4), default=0, comment="营销流量占比"),
        sa.Column("other_traffic_ratio", sa.DECIMAL(10, 4), default=0, comment="其他流量占比"),
        sa.Column("live_exposure_users", sa.Integer(), default=0, comment="直播间曝光人数"),
        sa.Column("live_enter_users", sa.Integer(), default=0, comment="直播进入人数"),
        sa.Column("card_click_users", sa.Integer(), default=0, comment="小风车/讲解卡点击人数"),
        sa.Column("private_message_count", sa.Integer(), default=0, comment="私信人数"),
        sa.Column("scene_leads_count", sa.Integer(), default=0, comment="全场景线索人数"),
        sa.Column("mini_windmill_click_count", sa.Integer(), default=0, comment="小风车点击次数"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
        comment="[DE] 直播场次主播汇总宽表 — 每场直播1条",
    )
    op.create_index("idx_de_summary_stat_date", "de_live_session_anchor_summary", ["stat_date"])
    op.create_index("idx_de_summary_anchor", "de_live_session_anchor_summary", ["anchor_name"])

    # ### de_anchor_realtime_metrics — 分钟级实时指标
    op.create_table(
        "de_anchor_realtime_metrics",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="ID"),
        sa.Column("session_id", sa.Integer(), nullable=False, comment="关联直播场次ID"),
        sa.Column("anchor_name", sa.String(100), nullable=True, comment="主播名称"),
        sa.Column("session_title", sa.String(200), nullable=True, comment="直播标题"),
        sa.Column("metric_time", sa.DateTime(), nullable=False, comment="指标时间（分钟级）"),
        sa.Column("avg_online_count", sa.DECIMAL(10, 1), default=0, comment="平均在线人数"),
        sa.Column("max_online_count", sa.Integer(), default=0, comment="最大在线人数"),
        sa.Column("avg_exposure_count", sa.DECIMAL(10, 1), default=0, comment="平均曝光次数"),
        sa.Column("avg_enter_count", sa.DECIMAL(10, 1), default=0, comment="平均进入人数"),
        sa.Column("total_like_count", sa.Integer(), default=0, comment="累计点赞量"),
        sa.Column("total_comment_count", sa.Integer(), default=0, comment="累计评论量"),
        sa.Column("total_follow_count", sa.Integer(), default=0, comment="累计关注量"),
        sa.Column("avg_natural_traffic", sa.DECIMAL(10, 1), default=0, comment="平均自然流量"),
        sa.Column("avg_marketing_traffic", sa.DECIMAL(10, 1), default=0, comment="平均营销流量"),
        sa.Column("metric_count", sa.Integer(), default=0, comment="聚合的原始记录数"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        comment="[DE] 分钟级实时指标 — 每场直播每分钟1条",
    )
    op.create_index("idx_de_metrics_session_time", "de_anchor_realtime_metrics", ["session_id", "metric_time"])

    # ### de_anchor_conversion_funnel — 转化漏斗
    op.create_table(
        "de_anchor_conversion_funnel",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="ID"),
        sa.Column("session_id", sa.Integer(), nullable=False, comment="关联直播场次ID"),
        sa.Column("anchor_name", sa.String(100), nullable=True, comment="主播名称"),
        sa.Column("session_title", sa.String(200), nullable=True, comment="直播标题"),
        sa.Column("stat_date", sa.Date(), nullable=True, comment="统计日期"),
        sa.Column("funnel_step", sa.String(20), nullable=False, comment="漏斗步骤"),
        sa.Column("user_count", sa.Integer(), default=0, comment="本步用户数"),
        sa.Column("prev_step_user_count", sa.Integer(), default=0, comment="上一步用户数"),
        sa.Column("step_rate", sa.DECIMAL(10, 4), default=0, comment="本步转化率"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        comment="[DE] 转化漏斗 — 每场5步：曝光→进入→点击→私信→留资",
    )
    op.create_index("idx_de_funnel_session", "de_anchor_conversion_funnel", ["session_id"])

    # ### de_anchor_audience_profile — 用户画像
    op.create_table(
        "de_anchor_audience_profile",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="ID"),
        sa.Column("session_id", sa.Integer(), nullable=False, comment="关联直播场次ID"),
        sa.Column("anchor_name", sa.String(100), nullable=True, comment="主播名称"),
        sa.Column("session_title", sa.String(200), nullable=True, comment="直播标题"),
        sa.Column("dimension_type", sa.String(20), nullable=False, comment="维度类型"),
        sa.Column("dimension_name", sa.String(50), nullable=False, comment="维度名称"),
        sa.Column("ratio", sa.DECIMAL(10, 4), default=0, comment="占比"),
        sa.Column("count", sa.Integer(), default=0, comment="人数"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        comment="[DE] 用户画像 — 年龄/性别/地域分布",
    )
    op.create_index("idx_de_profile_session", "de_anchor_audience_profile", ["session_id"])

    # ### de_anchor_comment_summary — 评论汇总
    op.create_table(
        "de_anchor_comment_summary",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="ID"),
        sa.Column("session_id", sa.Integer(), nullable=False, comment="关联直播场次ID"),
        sa.Column("anchor_name", sa.String(100), nullable=True, comment="主播名称"),
        sa.Column("session_title", sa.String(200), nullable=True, comment="直播标题"),
        sa.Column("stat_date", sa.Date(), nullable=True, comment="统计日期"),
        sa.Column("total_comments", sa.Integer(), default=0, comment="总评论数"),
        sa.Column("high_intent_count", sa.Integer(), default=0, comment="高意向评论数"),
        sa.Column("positive_count", sa.Integer(), default=0, comment="正面情绪评论数"),
        sa.Column("neutral_count", sa.Integer(), default=0, comment="中性情绪评论数"),
        sa.Column("negative_count", sa.Integer(), default=0, comment="负面情绪评论数"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
        comment="[DE] 评论汇总 — 每场直播1条",
    )

    # ### de_anchor_transcript_summary — 话术汇总
    op.create_table(
        "de_anchor_transcript_summary",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="ID"),
        sa.Column("session_id", sa.Integer(), nullable=False, comment="关联直播场次ID"),
        sa.Column("anchor_name", sa.String(100), nullable=True, comment="主播名称"),
        sa.Column("session_title", sa.String(200), nullable=True, comment="直播标题"),
        sa.Column("total_segments", sa.Integer(), default=0, comment="话术分段数"),
        sa.Column("total_text_length", sa.Integer(), default=0, comment="完整话术长度（字符数）"),
        sa.Column("avg_ai_score", sa.DECIMAL(3, 1), nullable=True, comment="平均AI评分（0-10）"),
        sa.Column("asr_status", sa.String(20), default="pending", comment="ASR状态"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
        comment="[DE] 话术汇总 — 每场直播1条",
    )

    # ### de_anchor_ai_analysis_summary — AI 分析汇总（Phase 7 填充数据）
    op.create_table(
        "de_anchor_ai_analysis_summary",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="ID"),
        sa.Column("session_id", sa.Integer(), nullable=False, comment="关联直播场次ID"),
        sa.Column("anchor_name", sa.String(100), nullable=True, comment="主播名称"),
        sa.Column("session_title", sa.String(200), nullable=True, comment="直播标题"),
        sa.Column("ai_total_score", sa.DECIMAL(3, 1), nullable=True, comment="AI综合评分"),
        sa.Column("completeness_score", sa.DECIMAL(3, 1), nullable=True, comment="完整性评分"),
        sa.Column("interactivity_score", sa.DECIMAL(3, 1), nullable=True, comment="互动性评分"),
        sa.Column("lead_guidance_score", sa.DECIMAL(3, 1), nullable=True, comment="留资引导评分"),
        sa.Column("report_count", sa.Integer(), default=0, comment="分析报告数量"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
        comment="[DE] AI分析汇总 — 每场直播1条，Phase7填充数据",
    )


def downgrade() -> None:
    op.drop_table("de_anchor_ai_analysis_summary")
    op.drop_table("de_anchor_transcript_summary")
    op.drop_table("de_anchor_comment_summary")
    op.drop_table("de_anchor_audience_profile")
    op.drop_table("de_anchor_conversion_funnel")
    op.drop_table("de_anchor_realtime_metrics")
    op.drop_table("de_live_session_anchor_summary")
