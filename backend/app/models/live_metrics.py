"""直播指标时间序列表 - 每30-60秒采一条"""
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, DECIMAL, ForeignKey, Index
from app.models.base import Base, TimestampMixin


class LiveMetric(Base, TimestampMixin):
    """直播指标时间序列"""

    __tablename__ = "live_metrics"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="ID")
    session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=False, comment="关联直播场次ID")
    metric_time = Column(DateTime, nullable=False, comment="指标采集时间")

    # 流量趋势
    exposure_count = Column(Integer, default=0, comment="曝光次数")
    online_count = Column(Integer, default=0, comment="在线人数")
    enter_count = Column(Integer, default=0, comment="进入人数")
    enter_fans_count = Column(Integer, default=0, comment="进入粉丝数")
    leave_count = Column(Integer, default=0, comment="离开人数")
    like_count = Column(Integer, default=0, comment="点赞量")
    comment_count = Column(Integer, default=0, comment="评论量")
    follow_count = Column(Integer, default=0, comment="关注次数")
    natural_traffic_count = Column(Integer, default=0, comment="自然流量数")
    marketing_traffic_count = Column(Integer, default=0, comment="营销流量数")

    __table_args__ = (
        Index("idx_session_metric_time", "session_id", "metric_time"),
    )
