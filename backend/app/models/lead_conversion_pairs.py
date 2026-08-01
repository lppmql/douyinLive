"""由分离的抖音号记录和联系方式记录组成的确认客资。"""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint

from app.models.base import Base, TimestampMixin


class LeadConversionPair(Base, TimestampMixin):
    """同主播、60秒内一对一配对成功的真实客资。"""

    __tablename__ = "lead_conversion_pairs"
    __table_args__ = (
        UniqueConstraint("douyin_lead_id", name="uq_lead_conversion_pairs_douyin"),
        UniqueConstraint("contact_lead_id", name="uq_lead_conversion_pairs_contact"),
        Index("idx_lead_conversion_pairs_session_time", "session_id", "converted_at", "id"),
        Index("idx_lead_conversion_pairs_douyin_id", "douyin_id"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="配对ID")
    douyin_lead_id = Column(
        Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, comment="提供客户抖音号的原始记录ID"
    )
    contact_lead_id = Column(
        Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, comment="提供手机号或微信号的原始记录ID"
    )
    session_id = Column(
        Integer, ForeignKey("live_sessions.id", ondelete="SET NULL"), nullable=True, comment="按主播和抖音号归属的直播场次ID"
    )
    anchor_name = Column(String(100), nullable=False, comment="两条原始记录共同的主播维度")
    douyin_id = Column(String(100), nullable=False, comment="客户公开抖音号")
    contact_type = Column(String(20), nullable=False, comment="联系方式类型：phone/wechat")
    contact_value = Column(String(100), nullable=False, comment="真实手机号或微信号")
    douyin_recorded_at = Column(DateTime, nullable=False, comment="抖音号原始记录时间")
    contact_recorded_at = Column(DateTime, nullable=False, comment="联系方式原始记录时间")
    converted_at = Column(DateTime, nullable=False, comment="两项资料均完成的时间")
    gap_seconds = Column(Integer, nullable=False, comment="两条记录绝对时间差秒数")
    attribution_status = Column(String(20), nullable=False, default="paired", comment="paired/attributed")
    attribution_method = Column(String(50), nullable=False, default="anchor_60s_pair", comment="配对与场次归属依据")
