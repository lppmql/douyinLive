"""phase 19 align task column comments

Revision ID: r1d2e3f4a5b6
Revises: q1d2e3f4a5b6
"""
from alembic import op


revision = "r1d2e3f4a5b6"
down_revision = "q1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE scraper_tasks
          MODIFY idempotency_key VARCHAR(100) NULL COMMENT '幂等键，防止任务重复提交',
          MODIFY trace_id VARCHAR(64) NULL COMMENT '任务链路追踪ID',
          MODIFY worker_id VARCHAR(100) NULL COMMENT '当前执行Worker',
          MODIFY priority INT NOT NULL DEFAULT 50 COMMENT '优先级，数值越小越优先'
        """
    )
    op.execute(
        """
        ALTER TABLE asr_tasks
          MODIFY idempotency_key VARCHAR(100) NULL COMMENT '幂等键，防止重复转写',
          MODIFY trace_id VARCHAR(64) NULL COMMENT '任务链路追踪ID',
          MODIFY worker_id VARCHAR(100) NULL COMMENT '当前执行Worker',
          MODIFY priority INT NOT NULL DEFAULT 50 COMMENT '优先级，数值越小越优先'
        """
    )
    op.execute(
        """
        ALTER TABLE asr_audio_chunks
          MODIFY id BIGINT NOT NULL AUTO_INCREMENT COMMENT '分片ID',
          MODIFY task_id BIGINT NOT NULL COMMENT 'ASR任务ID',
          MODIFY session_id INT NOT NULL COMMENT '直播场次ID',
          MODIFY chunk_index INT NOT NULL COMMENT '从0开始的分片序号',
          MODIFY start_seconds FLOAT NOT NULL DEFAULT 0 COMMENT '分片开始秒数',
          MODIFY end_seconds FLOAT NULL COMMENT '分片结束秒数，空表示读取到流结束',
          MODIFY source_url_hash VARCHAR(64) NOT NULL COMMENT '真实流地址哈希，不保存敏感URL副本',
          MODIFY status VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT 'pending/processing/completed/failed',
          MODIFY segment_count INT NOT NULL DEFAULT 0 COMMENT '已保存话术片段数',
          MODIFY retry_count INT NOT NULL DEFAULT 0 COMMENT '分片已执行次数',
          MODIFY max_retries INT NOT NULL DEFAULT 2 COMMENT '分片最大执行次数',
          MODIFY worker_id VARCHAR(100) NULL COMMENT '当前执行Worker',
          MODIFY heartbeat_at DATETIME NULL COMMENT '最近心跳时间',
          MODIFY started_at DATETIME NULL COMMENT '开始时间',
          MODIFY completed_at DATETIME NULL COMMENT '完成时间',
          MODIFY error_message TEXT NULL COMMENT '失败原因',
          MODIFY created_at DATETIME NOT NULL COMMENT '创建时间',
          MODIFY updated_at DATETIME NOT NULL COMMENT '更新时间'
        """
    )


def downgrade() -> None:
    # 字段说明不影响业务数据；降级保留说明，避免执行大表无意义重写。
    pass
