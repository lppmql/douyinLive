"""ASR 音频分片断点表。"""
from sqlalchemy import BigInteger, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text

from app.models.base import Base, TimestampMixin


class AsrAudioChunk(Base, TimestampMixin):
    """记录真实直播回放的转写进度，Worker 重启后可从未完成分片继续。"""

    __tablename__ = "asr_audio_chunks"
    __table_args__ = (
        Index("uq_asr_audio_chunks_task_index", "task_id", "chunk_index", unique=True),
        Index("idx_asr_audio_chunks_status", "status", "task_id", "chunk_index"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="分片ID")
    task_id = Column(BigInteger, ForeignKey("asr_tasks.id"), nullable=False, comment="ASR任务ID")
    session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=False, comment="直播场次ID")
    chunk_index = Column(Integer, nullable=False, comment="从0开始的分片序号")
    start_seconds = Column(Float, nullable=False, default=0, comment="分片开始秒数")
    end_seconds = Column(Float, nullable=True, comment="分片结束秒数，空表示读取到流结束")
    source_url_hash = Column(String(64), nullable=False, comment="真实流地址哈希，不保存敏感URL副本")
    status = Column(String(20), nullable=False, default="pending", comment="pending/processing/completed/failed")
    segment_count = Column(Integer, nullable=False, default=0, comment="已保存话术片段数")
    retry_count = Column(Integer, nullable=False, default=0, comment="分片已执行次数")
    max_retries = Column(Integer, nullable=False, default=2, comment="分片最大执行次数")
    worker_id = Column(String(100), nullable=True, comment="当前执行Worker")
    heartbeat_at = Column(DateTime, nullable=True, comment="最近心跳时间")
    started_at = Column(DateTime, nullable=True, comment="开始时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")
    error_message = Column(Text, nullable=True, comment="失败原因")
