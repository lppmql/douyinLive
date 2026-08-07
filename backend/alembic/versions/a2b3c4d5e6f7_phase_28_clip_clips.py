"""Add AI clip clips table.

Revision ID: a2b3c4d5e6f7
Revises: h8c9d0e1f2a3 (phase_42, 迁移链当前 head)
"""
from alembic import op
import sqlalchemy as sa


revision = "a2b3c4d5e6f7"
down_revision = "h8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clip_clips",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="成片ID"),
        sa.Column("task_id", sa.BigInteger(), nullable=True, comment="最近一次生成该成片的剪辑任务ID"),
        sa.Column("session_id", sa.Integer(), nullable=False, comment="关联直播场次ID"),
        sa.Column("clip_order", sa.Integer(), nullable=False, server_default="1", comment="场次内序号 1-5"),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="draft",
            comment="状态: draft(待确认)/approved(已确认)/discarded(已丢弃)/failed(生成失败)",
        ),
        sa.Column("title", sa.String(length=200), nullable=True, comment="抖音发布标题（AI 生成）"),
        sa.Column("description", sa.Text(), nullable=True, comment="发布文案（AI 生成）"),
        sa.Column("topics_json", sa.JSON(), nullable=True, comment="话题标签数组"),
        sa.Column("segments_json", sa.JSON(), nullable=False, comment="剪辑片段数组 [{start, end, text}]"),
        sa.Column("duration_seconds", sa.Integer(), nullable=True, comment="成片总时长（秒）"),
        sa.Column("video_path", sa.String(length=500), nullable=True, comment="成片文件相对 data/videos 的路径"),
        sa.Column("cover_path", sa.String(length=500), nullable=True, comment="封面图相对 data/videos 的路径"),
        sa.Column("subtitle_path", sa.String(length=500), nullable=True, comment="ASS 字幕文件相对路径"),
        sa.Column("source_text", sa.Text(), nullable=True, comment="AI 选段依据的话术摘要"),
        sa.Column("ai_raw_json", sa.JSON(), nullable=True, comment="AI 原始返回"),
        sa.Column("is_manual", sa.Integer(), nullable=False, server_default="0", comment="是否人工重剪: 1是 0否"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="生成失败原因"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.ForeignKeyConstraint(["session_id"], ["live_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["scraper_tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_clip_clips_session_status", "clip_clips", ["session_id", "status"], unique=False)
    op.create_index("idx_clip_clips_task", "clip_clips", ["task_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_clip_clips_task", table_name="clip_clips")
    op.drop_index("idx_clip_clips_session_status", table_name="clip_clips")
    op.drop_table("clip_clips")
