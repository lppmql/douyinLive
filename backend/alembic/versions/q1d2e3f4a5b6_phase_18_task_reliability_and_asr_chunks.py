"""phase 18 task reliability and ASR chunks

Revision ID: q1d2e3f4a5b6
Revises: p1d2e3f4a5b6
"""
from alembic import op
import sqlalchemy as sa


revision = "q1d2e3f4a5b6"
down_revision = "p1d2e3f4a5b6"
branch_labels = None
depends_on = None


def _add_runtime_columns(table_name: str, default_max_retries: str, idempotency_comment: str) -> None:
    op.add_column(table_name, sa.Column("idempotency_key", sa.String(100), nullable=True, comment=idempotency_comment))
    op.add_column(table_name, sa.Column("trace_id", sa.String(64), nullable=True, comment="任务链路追踪ID"))
    op.add_column(table_name, sa.Column("worker_id", sa.String(100), nullable=True, comment="当前执行Worker"))
    op.add_column(table_name, sa.Column("heartbeat_at", sa.DateTime(), nullable=True, comment="最近心跳时间"))
    op.add_column(table_name, sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0", comment="已执行次数"))
    op.add_column(table_name, sa.Column("max_retries", sa.Integer(), nullable=False, server_default=default_max_retries, comment="最大执行次数"))
    op.add_column(table_name, sa.Column("priority", sa.Integer(), nullable=False, server_default="50", comment="优先级，数值越小越优先"))
    op.create_index(f"idx_{table_name}_idempotency", table_name, ["idempotency_key"], unique=True)
    op.create_index(f"idx_{table_name}_trace", table_name, ["trace_id"])


def upgrade() -> None:
    _add_runtime_columns("scraper_tasks", "2", "幂等键，防止任务重复提交")
    _add_runtime_columns("asr_tasks", "3", "幂等键，防止重复转写")

    op.create_table(
        "asr_audio_chunks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="分片ID"),
        sa.Column("task_id", sa.BigInteger(), nullable=False, comment="ASR任务ID"),
        sa.Column("session_id", sa.Integer(), nullable=False, comment="直播场次ID"),
        sa.Column("chunk_index", sa.Integer(), nullable=False, comment="从0开始的分片序号"),
        sa.Column("start_seconds", sa.Float(), nullable=False, server_default="0", comment="分片开始秒数"),
        sa.Column("end_seconds", sa.Float(), nullable=True, comment="分片结束秒数，空表示读取到流结束"),
        sa.Column("source_url_hash", sa.String(64), nullable=False, comment="真实流地址哈希，不保存敏感URL副本"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending", comment="pending/processing/completed/failed"),
        sa.Column("segment_count", sa.Integer(), nullable=False, server_default="0", comment="已保存话术片段数"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0", comment="分片已执行次数"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="2", comment="分片最大执行次数"),
        sa.Column("worker_id", sa.String(100), nullable=True, comment="当前执行Worker"),
        sa.Column("heartbeat_at", sa.DateTime(), nullable=True, comment="最近心跳时间"),
        sa.Column("started_at", sa.DateTime(), nullable=True, comment="开始时间"),
        sa.Column("completed_at", sa.DateTime(), nullable=True, comment="完成时间"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="失败原因"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.ForeignKeyConstraint(["session_id"], ["live_sessions.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["asr_tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_asr_audio_chunks_task_index", "asr_audio_chunks", ["task_id", "chunk_index"], unique=True)
    op.create_index("idx_asr_audio_chunks_status", "asr_audio_chunks", ["status", "task_id", "chunk_index"])

    op.add_column("transcript_segments", sa.Column("asr_chunk_id", sa.BigInteger(), nullable=True, comment="关联ASR音频分片"))
    op.create_foreign_key(
        "fk_transcript_segments_asr_chunk_id",
        "transcript_segments",
        "asr_audio_chunks",
        ["asr_chunk_id"],
        ["id"],
    )
    op.create_index("idx_transcript_segments_asr_chunk", "transcript_segments", ["asr_chunk_id", "segment_start"])


def downgrade() -> None:
    op.drop_index("idx_transcript_segments_asr_chunk", table_name="transcript_segments")
    op.drop_constraint("fk_transcript_segments_asr_chunk_id", "transcript_segments", type_="foreignkey")
    op.drop_column("transcript_segments", "asr_chunk_id")
    op.drop_index("idx_asr_audio_chunks_status", table_name="asr_audio_chunks")
    op.drop_index("uq_asr_audio_chunks_task_index", table_name="asr_audio_chunks")
    op.drop_table("asr_audio_chunks")

    for table_name in ("asr_tasks", "scraper_tasks"):
        op.drop_index(f"idx_{table_name}_trace", table_name=table_name)
        op.drop_index(f"idx_{table_name}_idempotency", table_name=table_name)
        for column in ("priority", "max_retries", "retry_count", "heartbeat_at", "worker_id", "trace_id", "idempotency_key"):
            op.drop_column(table_name, column)
