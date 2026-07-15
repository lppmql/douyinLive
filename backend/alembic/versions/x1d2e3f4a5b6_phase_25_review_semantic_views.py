"""phase 25 review workbench semantic views

Revision ID: x1d2e3f4a5b6
Revises: w1d2e3f4a5b6
"""

from alembic import op


revision = "x1d2e3f4a5b6"
down_revision = "w1d2e3f4a5b6"
branch_labels = None
depends_on = None


VIEW_NAMES = (
    "de_v_fact_script_asset",
    "de_v_fact_review_action",
    "de_v_fact_review_finding",
)


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS de_v_fact_live_session")
    op.execute(
        """
        CREATE VIEW de_v_fact_live_session AS
        SELECT
          id AS session_id, room_id,
          COALESCE(NULLIF(douyin_uid, ''), CONCAT('room:', room_id)) AS anchor_key,
          DATE(live_start_time) AS date_key, session_title, live_status,
          live_start_time AS platform_start_time, live_end_time AS platform_end_time,
          live_duration_seconds, total_viewers, avg_online_count, peak_online_count,
          avg_watch_seconds, comments_count, comment_users, like_count, new_followers,
          private_message_count, private_message_longterm_count,
          leads_count, scene_leads_count, ad_cost, exposure_enter_rate, follow_rate,
          comment_rate, interaction_rate, scene_lead_conversion_rate,
          created_at AS collected_at, updated_at AS source_updated_at
        FROM live_sessions
        """
    )
    op.execute(
        """
        CREATE VIEW de_v_fact_review_finding AS
        SELECT
            rf.id AS finding_id,
            rf.session_id,
            ls.room_id,
            ls.anchor_name,
            ls.douyin_id,
            ls.session_title,
            ls.live_start_time AS platform_start_time,
            rf.finding_type,
            rf.category,
            rf.title,
            rf.description,
            rf.severity,
            rf.start_seconds,
            rf.end_seconds,
            rf.evidence_type,
            rf.evidence_text,
            rf.metric_name,
            rf.metric_before,
            rf.metric_after,
            rf.confidence,
            rf.source,
            rf.status,
            rf.created_at,
            rf.updated_at
        FROM review_findings rf
        INNER JOIN live_sessions ls ON ls.id = rf.session_id
        """
    )
    op.execute(
        """
        CREATE VIEW de_v_fact_review_action AS
        SELECT
            ra.id AS action_id,
            ra.session_id,
            ls.room_id,
            ls.anchor_name,
            ls.douyin_id,
            ls.session_title,
            ls.live_start_time AS platform_start_time,
            ra.finding_id,
            rf.finding_type,
            rf.category AS finding_category,
            ra.title,
            ra.description,
            ra.owner_name,
            ra.priority,
            ra.status,
            ra.due_at,
            ra.verification_session_id,
            verify_ls.live_start_time AS verification_platform_start_time,
            ra.verification_note,
            ra.created_at,
            ra.updated_at
        FROM review_action_items ra
        INNER JOIN live_sessions ls ON ls.id = ra.session_id
        LEFT JOIN review_findings rf ON rf.id = ra.finding_id
        LEFT JOIN live_sessions verify_ls ON verify_ls.id = ra.verification_session_id
        """
    )
    op.execute(
        """
        CREATE VIEW de_v_fact_script_asset AS
        SELECT
            sa.id AS asset_id,
            sa.session_id,
            ls.room_id,
            ls.anchor_name,
            ls.douyin_id,
            ls.session_title,
            ls.live_start_time AS platform_start_time,
            sa.transcript_segment_id,
            sa.category,
            sa.title,
            sa.content,
            sa.start_seconds,
            sa.end_seconds,
            sa.performance_note,
            sa.status,
            sa.created_at,
            sa.updated_at
        FROM script_assets sa
        INNER JOIN live_sessions ls ON ls.id = sa.session_id
        """
    )


def downgrade() -> None:
    for view_name in VIEW_NAMES:
        op.execute(f"DROP VIEW IF EXISTS {view_name}")
    op.execute("DROP VIEW IF EXISTS de_v_fact_live_session")
    op.execute(
        """
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
        """
    )
