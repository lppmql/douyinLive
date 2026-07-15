"""直播知识时间片模型。"""
from sqlalchemy import BigInteger, Column, DateTime, DECIMAL, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT

from app.models.base import Base, TimestampMixin


class KnowledgeTimeSlice(Base, TimestampMixin):
    """把话术、评论和指标按固定直播时间窗口绑定。"""

    __tablename__ = "knowledge_time_slices"
    __table_args__ = (
        UniqueConstraint("session_id", "slice_index", name="uq_kb_slice_session_index"),
        Index("idx_kb_slice_session_seconds", "session_id", "slice_start_seconds"),
        Index("idx_kb_slice_anchor_time", "anchor_name", "slice_start_time"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="知识时间片ID")
    session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=False, comment="关联直播场次ID")
    slice_index = Column(Integer, nullable=False, comment="场次内时间片序号，从0开始")
    slice_start_seconds = Column(Integer, nullable=False, comment="相对开播开始秒数")
    slice_end_seconds = Column(Integer, nullable=False, comment="相对开播结束秒数")
    slice_start_time = Column(DateTime, nullable=True, comment="平台时间片开始时间")
    slice_end_time = Column(DateTime, nullable=True, comment="平台时间片结束时间")
    anchor_name = Column(String(100), nullable=True, comment="主播名称快照")
    session_title = Column(String(200), nullable=True, comment="直播标题快照")
    transcript_text = Column(LONGTEXT, nullable=True, comment="本时间片真实话术")
    comments_text = Column(LONGTEXT, nullable=True, comment="本时间片真实评论")
    comment_count = Column(Integer, nullable=False, default=0, comment="已准确映射评论数")
    high_intent_comment_count = Column(Integer, nullable=False, default=0, comment="高意向评论数")
    unmapped_comment_count = Column(Integer, nullable=False, default=0, comment="因缺少平台时间未映射评论数")
    metric_point_count = Column(Integer, nullable=False, default=0, comment="指标采样点数")
    avg_online_count = Column(DECIMAL(10, 2), nullable=False, default=0, comment="时间片平均在线人数")
    peak_online_count = Column(Integer, nullable=False, default=0, comment="时间片峰值在线人数")
    metric_summary_json = Column(Text, nullable=True, comment="时间片指标摘要JSON")
    search_text = Column(LONGTEXT, nullable=True, comment="用于混合检索的规范化文本")
    source_hash = Column(String(64), nullable=False, comment="源数据哈希，用于幂等更新")
    parser_version = Column(String(30), nullable=False, default="time-slice-v1", comment="时间片解析器版本")
