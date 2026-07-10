"""直播间信息表"""
from sqlalchemy import Column, Integer, String, Boolean
from app.models.base import Base, TimestampMixin


class LiveRoom(Base, TimestampMixin):
    """直播间信息"""

    __tablename__ = "live_rooms"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="直播间ID")
    account_name = Column(String(100), nullable=False, comment="账号名称")
    anchor_name = Column(String(100), nullable=False, comment="主播名称")
    anchor_nickname = Column(String(100), nullable=True, comment="主播昵称/展示名")
    anchor_avatar_url = Column(String(500), nullable=True, comment="主播头像 URL")
    douyin_id = Column(String(100), nullable=True, comment="抖音号")
    douyin_uid = Column(String(100), nullable=True, comment="抖音 UID")
    room_id_str = Column(String(100), nullable=True, comment="直播间原始ID")
    team_name = Column(String(100), nullable=True, comment="所属团队/组")
    platform = Column(String(20), default="douyin", comment="平台")
    status = Column(Boolean, default=True, comment="状态：1启用 0停用")
