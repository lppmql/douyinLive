"""主播话术分段表"""
from sqlalchemy import Column, Integer, BigInteger, String, Text, DECIMAL, ForeignKey, Index
from app.models.base import Base, TimestampMixin


class TranscriptSegment(Base, TimestampMixin):
    """主播话术分段 - 带时间戳、转写状态、AI评分"""

    __tablename__ = "transcript_segments"
    __table_args__ = (
        Index("idx_transcript_segments_asr_chunk", "asr_chunk_id", "segment_start"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="ID")
    session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=False, comment="关联直播场次ID")
    asr_chunk_id = Column(BigInteger, ForeignKey("asr_audio_chunks.id"), nullable=True, comment="关联ASR音频分片")
    segment_start = Column(DECIMAL(10, 1), nullable=True, comment="片段开始时间（秒）")
    segment_end = Column(DECIMAL(10, 1), nullable=True, comment="片段结束时间（秒）")
    text_content = Column(Text, nullable=True, comment="话术内容")
    segment_type = Column(String(50), nullable=True, comment="话术类型：开场/产品介绍/互动/留资引导/结束")
    asr_status = Column(String(20), default="pending", comment="转写状态：pending/processing/completed/failed")
    ai_score = Column(DECIMAL(3, 1), nullable=True, comment="AI评分（0-10）")
    is_high_conversion = Column(Integer, default=0, comment="是否高转化话术：1是 0否")
