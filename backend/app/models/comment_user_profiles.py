"""评论用户公开资料缓存。"""

from sqlalchemy import Column, DateTime, Index, Integer, String

from app.models.base import Base, TimestampMixin


class CommentUserProfile(Base, TimestampMixin):
    """按 sec_uid 缓存真实公开资料，避免跨场次重复请求抖音。"""

    __tablename__ = "comment_user_profiles"
    __table_args__ = (
        Index("idx_comment_user_profiles_status_retry", "fetch_status", "retry_after", "id"),
        Index("idx_comment_user_profiles_public_id", "public_douyin_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    sec_uid = Column(String(200), nullable=False, unique=True, comment="评论用户稳定SecUID")
    nickname = Column(String(100), nullable=True, comment="最近一次获取的公开昵称")
    avatar_url = Column(String(1000), nullable=True, comment="公开头像 URL")
    unique_id = Column(String(100), nullable=True, comment="用户自定义抖音号")
    short_id = Column(String(100), nullable=True, comment="平台数字短号")
    public_douyin_id = Column(String(100), nullable=True, comment="用于展示与匹配的首选公开抖音号")
    douyin_id_type = Column(String(20), nullable=True, comment="公开抖音号类型：unique_id/short_id")
    profile_source = Column(String(50), nullable=False, default="iesdouyin_user_info", comment="公开资料来源")
    fetch_status = Column(String(20), nullable=False, default="pending", comment="pending/running/success/partial/failed/blocked")
    last_fetched_at = Column(DateTime, nullable=True, comment="最近完成查询时间")
    retry_after = Column(DateTime, nullable=True, comment="失败后最早重试时间")
    failure_count = Column(Integer, nullable=False, default=0, comment="连续失败次数")
    last_error_code = Column(String(50), nullable=True, comment="脱敏错误代码")
