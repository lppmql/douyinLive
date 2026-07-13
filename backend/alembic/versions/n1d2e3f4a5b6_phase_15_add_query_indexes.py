"""phase 15 add high frequency query indexes

Revision ID: n1d2e3f4a5b6
Revises: m1d2e3f4a5b6
"""

from alembic import op


revision = "n1d2e3f4a5b6"
down_revision = "m1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("idx_live_sessions_status_room", "live_sessions", ["live_status", "room_id", "id"])
    op.create_index(
        "idx_live_sessions_detail_time",
        "live_sessions",
        ["detail_collection_status", "live_start_time"],
    )
    op.create_index("idx_comments_session_time", "comments", ["session_id", "comment_time", "id"])
    op.create_index("idx_comments_intent_time", "comments", ["is_high_intent", "comment_time"])
    op.create_index("idx_scraper_tasks_status_type", "scraper_tasks", ["status", "task_type", "id"])
    op.create_index("idx_scraper_logs_task_id", "scraper_logs", ["task_id", "id"])
    op.create_index("idx_scraper_logs_level_id", "scraper_logs", ["level", "id"])
    op.create_index("idx_asr_tasks_status_created", "asr_tasks", ["status", "created_at"])
    op.create_index(
        "idx_stream_sources_session_status_time",
        "stream_sources",
        ["session_id", "status", "fetched_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_stream_sources_session_status_time", table_name="stream_sources")
    op.drop_index("idx_asr_tasks_status_created", table_name="asr_tasks")
    op.drop_index("idx_scraper_logs_level_id", table_name="scraper_logs")
    op.drop_index("idx_scraper_logs_task_id", table_name="scraper_logs")
    op.drop_index("idx_scraper_tasks_status_type", table_name="scraper_tasks")
    op.drop_index("idx_comments_intent_time", table_name="comments")
    op.drop_index("idx_comments_session_time", table_name="comments")
    op.drop_index("idx_live_sessions_detail_time", table_name="live_sessions")
    op.drop_index("idx_live_sessions_status_room", table_name="live_sessions")
