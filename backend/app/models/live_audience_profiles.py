"""用户画像表"""
from sqlalchemy import Column, Integer, String, DECIMAL, ForeignKey
from app.models.base import Base, TimestampMixin


class LiveAudienceProfile(Base, TimestampMixin):
    """用户画像 - 年龄/性别/区域/省份/城市分布"""

    __tablename__ = "live_audience_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=False, comment="关联直播场次ID")
    dimension_type = Column(String(20), nullable=False, comment="维度类型：age/gender/region/province/city")
    dimension_name = Column(String(50), nullable=False, comment="维度名称，如31-40岁/男/广东")
    ratio = Column(DECIMAL(10, 4), default=0, comment="占比")
    count = Column(Integer, default=0, comment="人数")
