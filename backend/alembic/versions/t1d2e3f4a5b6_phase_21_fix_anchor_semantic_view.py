"""Fix anchor semantic view for ONLY_FULL_GROUP_BY.

Revision ID: t1d2e3f4a5b6
Revises: s1d2e3f4a5b6
"""
from alembic import op


revision = "t1d2e3f4a5b6"
down_revision = "s1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS de_v_dim_anchor")
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


def downgrade() -> None:
    # 视图字段未变化，降级时保留兼容 ONLY_FULL_GROUP_BY 的等价定义。
    op.execute("DROP VIEW IF EXISTS de_v_dim_anchor")
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
