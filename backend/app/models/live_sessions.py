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

    # 企业主账号下不同场次可能属于不同主播，必须按场次保存而不是只从直播间主表读取。
    anchor_name = Column(String(100), nullable=True, comment="本场主播名称")
    anchor_nickname = Column(String(100), nullable=True, comment="本场主播昵称")
    anchor_avatar_url = Column(String(500), nullable=True, comment="本场主播头像")
    douyin_id = Column(String(100), nullable=True, comment="本场主播抖音号")
    douyin_uid = Column(String(100), nullable=True, comment="本场主播抖音UID")
    detail_collection_status = Column(String(20), default="pending", comment="详情采集状态: pending/complete/retryable/unavailable")
    detail_collection_error = Column(String(500), nullable=True, comment="详情采集最近错误")

    # 时间
    live_start_time = Column(DateTime, nullable=True, comment="开播时间")
    live_end_time = Column(DateTime, nullable=True, comment="下播时间")
    live_duration_seconds = Column(Integer, default=0, comment="直播时长（秒）")
    live_status = Column(String(20), default="finished", comment="直播状态：liveing/ended")

    # 核心指标
    total_viewers = Column(Integer, default=0, comment="累计观看人数")
    viewed_count = Column(Integer, default=0, comment="看过人数")
    avg_online_count = Column(Integer, default=0, comment="平均在线人数")
    avg_watch_seconds = Column(DECIMAL(10, 1), default=0, comment="人均观看时长（秒）")
    fans_avg_watch_seconds = Column(DECIMAL(10, 1), default=0, comment="粉丝停留时长（秒）")
    peak_online_count = Column(Integer, default=0, comment="最高在线人数")
    realtime_online_count = Column(Integer, default=0, comment="实时在线人数")
    private_message_count = Column(Integer, default=0, comment="私信人数")
    private_message_longterm_count = Column(Integer, default=0, comment="私信长效转化人数")
    scene_leads_count = Column(Integer, default=0, comment="全场景线索人数")
    ad_cost = Column(DECIMAL(10, 2), default=0, comment="广告消耗（元）")
    mini_windmill_click_count = Column(Integer, default=0, comment="小风车点击次数")
    mini_windmill_click_rate = Column(DECIMAL(10, 4), default=0, comment="小风车点击率")
    card_click_count = Column(Integer, default=0, comment="卡片点击次数")
    card_click_rate = Column(DECIMAL(10, 4), default=0, comment="卡片点击率")
    new_followers = Column(Integer, default=0, comment="涨粉量")
    follow_rate = Column(DECIMAL(10, 4), default=0, comment="关注率")
    share_count = Column(Integer, default=0, comment="分享次数")
    share_users = Column(Integer, default=0, comment="分享人数")
    like_count = Column(Integer, default=0, comment="点赞次数")
    like_users = Column(Integer, default=0, comment="点赞人数")
    comment_users = Column(Integer, default=0, comment="评论人数")
    interaction_count = Column(Integer, default=0, comment="互动次数")
    interaction_users = Column(Integer, default=0, comment="互动人数")
    watch_count = Column(Integer, default=0, comment="观看次数")
    watch_over_1m_count = Column(Integer, default=0, comment="大于1分钟观看人次")
    fans_club_join_count = Column(Integer, default=0, comment="加粉丝团人数")
    fans_club_join_rate = Column(DECIMAL(10, 4), default=0, comment="加粉丝团率")
    gift_count = Column(Integer, default=0, comment="打赏次数")
    gift_amount = Column(DECIMAL(10, 2), default=0, comment="打赏金额")
    dislike_count = Column(Integer, default=0, comment="不感兴趣次数")
    dislike_users = Column(Integer, default=0, comment="不感兴趣人数")
    wechat_add_count = Column(Integer, default=0, comment="企业微信添加数")
    wechat_add_cost = Column(DECIMAL(10, 2), default=0, comment="企业微信添加成本")
    form_submit_count = Column(Integer, default=0, comment="表单提交数")
    form_submit_users = Column(Integer, default=0, comment="表单提交人数")
    form_submit_cost = Column(DECIMAL(10, 2), default=0, comment="表单提交成本")

    # 比率指标（统一 DECIMAL(10,4)，存小数，如 0.1427 = 14.27%）
    exposure_enter_rate = Column(DECIMAL(10, 4), default=0, comment="曝光进入率")
    fans_view_ratio = Column(DECIMAL(10, 4), default=0, comment="场观粉丝占比")
    scene_lead_conversion_rate = Column(DECIMAL(10, 4), default=0, comment="线索转化率")
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
