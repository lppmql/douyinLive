"""直播流源表 — m3u8 地址和请求头"""
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Index
from app.models.base import Base, TimestampMixin


class StreamSource(Base, TimestampMixin):
    """直播流源信息"""

    __tablename__ = "stream_sources"
    __table_args__ = (
        Index("idx_stream_sources_session_status_time", "session_id", "status", "fetched_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="流源ID")
    session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=False, comment="关联直播场次")
    source_type = Column(String(20), default="m3u8", comment="流源类型: m3u8/flv/hls")
    m3u8_url = Column(String(2000), nullable=False, comment="m3u8 播放地址")
    headers_json = Column(JSON, nullable=True, comment="请求头(Referer/User-Agent等)")
    quality = Column(String(20), nullable=True, comment="清晰度: origin/uhd/hd/sd")
    status = Column(String(20), default="active", comment="状态: active/expired/error")
    expires_at = Column(DateTime, nullable=True, comment="过期时间")
    fetched_at = Column(DateTime, nullable=True, comment="采集时间")
