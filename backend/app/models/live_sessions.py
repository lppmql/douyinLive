"""直播场次表 - 核心表"""
from sqlalchemy import Column, Integer, String, DateTime, DECIMAL, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.models.base import Base, TimestampMixin


class LiveSession(Base, TimestampMixin):
    """直播场次 - 包含所有核心指标、流量来源、转化漏斗"""

    __tablename__ = "live_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="场次ID")
    room_id = Column(Integer, ForeignKey("live_rooms.id"), nullable=False, comment="关联直播间ID")
    session_title = Column(String(200), nullable=True, comment="直播场次标题/名称")
    dashboard_url = Column(String(1000), nullable=True, comment="直播大屏页面URL")
    stream_url = Column(String(2000), nullable=True, comment="直播流m3u8地址")

    # 时间
    live_start_time = Column(DateTime, nullable=True, comment="开播时间")
    live_end_time = Column(DateTime, nullable=True, comment="下播时间")
    live_duration_seconds = Column(Integer, default=0, comment="直播时长（秒）")
    live_status = Column(String(20), default="finished", comment="直播状态：liveing/ended")

    # 核心指标
    total_viewers = Column(Integer, default=0, comment="累计观看人数")
    avg_watch_seconds = Column(DECIMAL(10, 1), default=0, comment="人均观看时长（秒）")
    peak_online_count = Column(Integer, default=0, comment="最高在线人数")
    realtime_online_count = Column(Integer, default=0, comment="实时在线人数")
    private_message_count = Column(Integer, default=0, comment="私信人数")
    scene_leads_count = Column(Integer, default=0, comment="全场景线索人数")
    ad_cost = Column(DECIMAL(10, 2), default=0, comment="广告消耗（元）")
    mini_windmill_click_count = Column(Integer, default=0, comment="小风车点击次数")
    new_followers = Column(Integer, default=0, comment="涨粉量")

    # 比率指标（统一 DECIMAL(10,4)，存小数，如 0.1427 = 14.27%）
    exposure_enter_rate = Column(DECIMAL(10, 4), default=0, comment="曝光进入率")
    share_rate = Column(DECIMAL(10, 4), default=0, comment="分享率")
    like_rate = Column(DECIMAL(10, 4), default=0, comment="点赞率")
    comment_rate = Column(DECIMAL(10, 4), default=0, comment="评论率")
    interaction_rate = Column(DECIMAL(10, 4), default=0, comment="互动率")
    comments_count = Column(Integer, default=0, comment="评论总数")
    leads_count = Column(Integer, default=0, comment="留资总数")

    # 流量来源
    natural_traffic_ratio = Column(DECIMAL(10, 4), default=0, comment="自然流量占比")
    marketing_traffic_ratio = Column(DECIMAL(10, 4), default=0, comment="营销流量占比")
    other_traffic_ratio = Column(DECIMAL(10, 4), default=0, comment="其他流量占比")

    # 转化漏斗
    live_exposure_users = Column(Integer, default=0, comment="直播间曝光人数")
    live_enter_users = Column(Integer, default=0, comment="直播进入人数")
    card_click_users = Column(Integer, default=0, comment="小风车/讲解卡点击人数")

    # 关联
    room = relationship("LiveRoom", backref="sessions")
