"""phase 43：逐字字幕、成片版本和多信号证据。

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
"""

from alembic import op
import sqlalchemy as sa


revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transcript_segments",
        sa.Column(
            "raw_text_content",
            sa.Text(),
            nullable=True,
            comment="FunASR 原始话术（纠错前）",
        ),
    )
    op.add_column(
        "transcript_segments",
        sa.Column(
            "word_timestamps_json",
            sa.JSON(),
            nullable=True,
            comment="纠错后逐字/词时间戳 [{text,start,end}]，时间为整场绝对秒数",
        ),
    )
    op.add_column(
        "transcript_segments",
        sa.Column(
            "timestamp_source",
            sa.String(length=30),
            nullable=True,
            comment="字幕时间来源：funasr_exact/funasr_aligned/funasr_remapped/segment_estimated",
        ),
    )

    op.add_column(
        "clip_clips",
        sa.Column(
            "theme", sa.String(length=200), nullable=True, comment="成片主题摘要"
        ),
    )
    op.add_column(
        "clip_clips",
        sa.Column(
            "subtitle_srt_path",
            sa.String(length=500),
            nullable=True,
            comment="SRT 字幕文件相对路径",
        ),
    )
    op.add_column(
        "clip_clips",
        sa.Column(
            "clean_video_path",
            sa.String(length=500),
            nullable=True,
            comment="无字幕底片相对路径，供快速重制字幕",
        ),
    )
    op.add_column(
        "clip_clips",
        sa.Column(
            "subtitle_precision",
            sa.String(length=30),
            nullable=False,
            server_default="segment_estimated",
            comment="字幕精度来源",
        ),
    )
    op.add_column(
        "clip_clips",
        sa.Column(
            "render_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="当前成片渲染版本",
        ),
    )
    op.add_column(
        "clip_clips",
        sa.Column(
            "artifact_versions_json",
            sa.JSON(),
            nullable=True,
            comment="历史成片版本及文件路径",
        ),
    )
    op.add_column(
        "clip_clips",
        sa.Column(
            "selection_evidence_json",
            sa.JSON(),
            nullable=True,
            comment="评论、互动、钩子、客资等选段证据",
        ),
    )
    op.add_column(
        "clip_clips",
        sa.Column("qc_json", sa.JSON(), nullable=True, comment="成片自动质检结果"),
    )


def downgrade() -> None:
    for column_name in (
        "qc_json",
        "selection_evidence_json",
        "artifact_versions_json",
        "render_version",
        "subtitle_precision",
        "clean_video_path",
        "subtitle_srt_path",
        "theme",
    ):
        op.drop_column("clip_clips", column_name)
    for column_name in ("timestamp_source", "word_timestamps_json", "raw_text_content"):
        op.drop_column("transcript_segments", column_name)
