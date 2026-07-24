"""Phase 35：所有引用 live_sessions 的外键添加 ON DELETE CASCADE

为以下表的外键添加级联删除，确保删除直播场次时自动清理关联数据：
  ai_call_traces, analysis_reports, asr_audio_chunks, asr_tasks,
  comments, high_intent_users, knowledge_base, knowledge_time_slices,
  leads, live_audience_profiles, live_metrics, review_action_items,
  review_findings, scraper_tasks, script_assets, stream_sources,
  transcript_full_texts, transcript_segments

Revision ID: a7d8e9f0b1c2
Revises: 7e4b9c2d1a66
Create Date: 2026-07-24
"""

from alembic import op
import sqlalchemy as sa

revision = "a7d8e9f0b1c2"
down_revision = "7e4b9c2d1a66"
branch_labels = None
depends_on = None

# (table, constraint, column, referenced_col)
FK_DEFINITIONS = [
    ("ai_call_traces", "ai_call_traces_ibfk_1", "session_id"),
    ("analysis_reports", "analysis_reports_ibfk_1", "session_id"),
    ("asr_audio_chunks", "asr_audio_chunks_ibfk_1", "session_id"),
    ("asr_tasks", "fk_asr_tasks_session", "session_id"),
    ("comments", "comments_ibfk_1", "session_id"),
    ("high_intent_users", "high_intent_users_ibfk_2", "session_id"),
    ("knowledge_base", "knowledge_base_ibfk_1", "session_id"),
    ("knowledge_time_slices", "knowledge_time_slices_ibfk_1", "session_id"),
    ("leads", "leads_ibfk_1", "session_id"),
    ("live_audience_profiles", "live_audience_profiles_ibfk_1", "session_id"),
    ("live_metrics", "live_metrics_ibfk_1", "session_id"),
    ("review_action_items", "review_action_items_ibfk_1", "session_id"),
    ("review_action_items", "review_action_items_ibfk_3", "verification_session_id"),
    ("review_findings", "review_findings_ibfk_1", "session_id"),
    ("scraper_tasks", "fk_scraper_tasks_session", "session_id"),
    ("script_assets", "script_assets_ibfk_1", "session_id"),
    ("stream_sources", "fk_stream_sources_session", "session_id"),
    ("transcript_full_texts", "transcript_full_texts_ibfk_1", "session_id"),
    ("transcript_segments", "transcript_segments_ibfk_1", "session_id"),
]


def _rebuild_fk(with_cascade: bool) -> None:
    """逐个删除旧外键并重建，with_cascade=True 时添加 ON DELETE CASCADE。"""
    cascade_clause = " ON DELETE CASCADE" if with_cascade else ""
    for table, constraint, column in FK_DEFINITIONS:
        try:
            op.drop_constraint(constraint, table, type_="foreignkey")
        except Exception:
            # 约束可能不存在（如已手动删除），跳过
            pass
        op.create_foreign_key(
            constraint,
            table,
            "live_sessions",
            [column],
            ["id"],
            ondelete="CASCADE" if with_cascade else None,
        )


def upgrade() -> None:
    _rebuild_fk(with_cascade=True)


def downgrade() -> None:
    _rebuild_fk(with_cascade=False)
