"""P1 knowledge time slices and DataEase semantic views.

Revision ID: s1d2e3f4a5b6
Revises: r1d2e3f4a5b6
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "s1d2e3f4a5b6"
down_revision = "r1d2e3f4a5b6"
branch_labels = None
depends_on = None


SEMANTIC_VIEWS = (
    "de_v_fact_ai_analysis",
    "de_v_fact_transcript_segment",
    "de_v_fact_comment",
    "de_v_fact_live_minute_metric",
    "de_v_fact_live_session",
    "de_v_dim_date",
    "de_v_dim_anchor",
)


def upgrade() -> None:
    op.create_table(
        "knowledge_time_slices",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="知识时间片ID"),
        sa.Column("session_id", sa.Integer(), nullable=False, comment="关联直播场次ID"),
        sa.Column("slice_index", sa.Integer(), nullable=False, comment="场次内时间片序号，从0开始"),
        sa.Column("slice_start_seconds", sa.Integer(), nullable=False, comment="相对开播开始秒数"),
        sa.Column("slice_end_seconds", sa.Integer(), nullable=False, comment="相对开播结束秒数"),
        sa.Column("slice_start_time", sa.DateTime(), nullable=True, comment="平台时间片开始时间"),
        sa.Column("slice_end_time", sa.DateTime(), nullable=True, comment="平台时间片结束时间"),
        sa.Column("anchor_name", sa.String(length=100), nullable=True, comment="主播名称快照"),
        sa.Column("session_title", sa.String(length=200), nullable=True, comment="直播标题快照"),
        sa.Column("transcript_text", mysql.LONGTEXT(), nullable=True, comment="本时间片真实话术"),
        sa.Column("comments_text", mysql.LONGTEXT(), nullable=True, comment="本时间片真实评论"),
        sa.Column("comment_count", sa.Integer(), server_default="0", nullable=False, comment="已准确映射评论数"),
        sa.Column("high_intent_comment_count", sa.Integer(), server_default="0", nullable=False, comment="高意向评论数"),
        sa.Column("unmapped_comment_count", sa.Integer(), server_default="0", nullable=False, comment="因缺少平台时间未映射评论数"),
        sa.Column("metric_point_count", sa.Integer(), server_default="0", nullable=False, comment="指标采样点数"),
        sa.Column("avg_online_count", sa.DECIMAL(10, 2), server_default="0", nullable=False, comment="时间片平均在线人数"),
        sa.Column("peak_online_count", sa.Integer(), server_default="0", nullable=False, comment="时间片峰值在线人数"),
        sa.Column("metric_summary_json", sa.Text(), nullable=True, comment="时间片指标摘要JSON"),
        sa.Column("search_text", mysql.LONGTEXT(), nullable=True, comment="用于混合检索的规范化文本"),
        sa.Column("source_hash", sa.String(length=64), nullable=False, comment="源数据哈希，用于幂等更新"),
        sa.Column("parser_version", sa.String(length=30), server_default="time-slice-v1", nullable=False, comment="时间片解析器版本"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.ForeignKeyConstraint(["session_id"], ["live_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "slice_index", name="uq_kb_slice_session_index"),
    )
    op.create_index("idx_kb_slice_session_seconds", "knowledge_time_slices", ["session_id", "slice_start_seconds"])
    op.create_index("idx_kb_slice_anchor_time", "knowledge_time_slices", ["anchor_name", "slice_start_time"])

    op.execute("""
        CREATE VIEW de_v_dim_anchor AS
        SELECT
          anchor_key,
          MAX(anchor_name) AS anchor_name,
          MAX(anchor_nickname) AS anchor_nickname,
          MAX(douyin_id) AS douyin_id,
          MAX(anchor_avatar_url) AS anchor_avatar_url,
          COUNT(*) AS session_count,
          MAX(updated_at) AS source_updated_at
        FROM (
          SELECT
            COALESCE(NULLIF(douyin_uid, ''), CONCAT('room:', room_id)) AS anchor_key,
            anchor_name, anchor_nickname, douyin_id, anchor_avatar_url, updated_at
          FROM live_sessions
        ) anchor_source
        GROUP BY anchor_key
    """)
    op.execute("""
        CREATE VIEW de_v_dim_date AS
        SELECT DISTINCT
          DATE(live_start_time) AS date_key,
          YEAR(live_start_time) AS year_number,
          QUARTER(live_start_time) AS quarter_number,
          MONTH(live_start_time) AS month_number,
          DAY(live_start_time) AS day_number,
          WEEKDAY(live_start_time) + 1 AS weekday_number
        FROM live_sessions WHERE live_start_time IS NOT NULL
    """)
    op.execute("""
        CREATE VIEW de_v_fact_live_session AS
        SELECT
          id AS session_id, room_id,
          COALESCE(NULLIF(douyin_uid, ''), CONCAT('room:', room_id)) AS anchor_key,
          DATE(live_start_time) AS date_key, session_title, live_status,
          live_start_time AS platform_start_time, live_end_time AS platform_end_time,
          live_duration_seconds, total_viewers, avg_online_count, peak_online_count,
          avg_watch_seconds, comments_count, comment_users, like_count, new_followers,
          leads_count, ad_cost, exposure_enter_rate, follow_rate, comment_rate,
          interaction_rate, scene_lead_conversion_rate,
          created_at AS collected_at, updated_at AS source_updated_at
        FROM live_sessions
    """)
    op.execute("""
        CREATE VIEW de_v_fact_live_minute_metric AS
        SELECT
          m.id AS metric_id, m.session_id,
          COALESCE(NULLIF(s.douyin_uid, ''), CONCAT('room:', s.room_id)) AS anchor_key,
          DATE(m.metric_time) AS date_key, m.metric_time AS platform_metric_time,
          m.exposure_count, m.online_count, m.enter_count, m.leave_count,
          m.like_count, m.comment_count, m.follow_count, m.clue_count,
          m.windmill_click_count, m.card_click_count, m.wechat_add_count,
          m.form_submit_count, m.cost_amount, m.natural_traffic_count,
          m.marketing_traffic_count, m.created_at AS collected_at, m.updated_at AS source_updated_at
        FROM live_metrics m JOIN live_sessions s ON s.id = m.session_id
    """)
    op.execute("""
        CREATE VIEW de_v_fact_comment AS
        SELECT
          c.id AS comment_id, c.session_id,
          COALESCE(NULLIF(s.douyin_uid, ''), CONCAT('room:', s.room_id)) AS anchor_key,
          DATE(c.comment_time) AS date_key, c.comment_time AS platform_comment_time,
          COALESCE(NULLIF(c.user_sec_uid, ''), NULLIF(c.webcast_uid, ''), CONCAT('comment:', c.id)) AS user_key,
          c.comment_content, c.is_high_intent, c.sentiment, c.keywords,
          c.created_at AS collected_at, c.updated_at AS source_updated_at
        FROM comments c JOIN live_sessions s ON s.id = c.session_id
    """)
    op.execute("""
        CREATE VIEW de_v_fact_transcript_segment AS
        SELECT
          t.id AS segment_id, t.session_id,
          COALESCE(NULLIF(s.douyin_uid, ''), CONCAT('room:', s.room_id)) AS anchor_key,
          DATE(s.live_start_time) AS date_key, s.live_start_time AS platform_start_time,
          t.segment_start, t.segment_end,
          t.text_content, t.segment_type, t.ai_score, t.is_high_conversion,
          t.created_at AS collected_at, t.updated_at AS source_updated_at
        FROM transcript_segments t JOIN live_sessions s ON s.id = t.session_id
        WHERE t.asr_status = 'completed'
    """)
    op.execute("""
        CREATE VIEW de_v_fact_ai_analysis AS
        SELECT
          a.id AS analysis_id, a.session_id,
          COALESCE(NULLIF(s.douyin_uid, ''), CONCAT('room:', s.room_id)) AS anchor_key,
          DATE(s.live_start_time) AS date_key, a.report_type, a.report_title,
          a.summary, a.report_content, a.created_at AS generated_at, a.updated_at AS source_updated_at
        FROM analysis_reports a JOIN live_sessions s ON s.id = a.session_id
    """)


def downgrade() -> None:
    for view_name in SEMANTIC_VIEWS:
        op.execute(f"DROP VIEW IF EXISTS {view_name}")
    op.drop_index("idx_kb_slice_anchor_time", table_name="knowledge_time_slices")
    op.drop_index("idx_kb_slice_session_seconds", table_name="knowledge_time_slices")
    op.drop_table("knowledge_time_slices")
