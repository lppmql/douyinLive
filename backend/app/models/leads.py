"""留资数据表。"""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, String

from app.models.base import Base, TimestampMixin


class Lead(Base, TimestampMixin):
    """留资数据 - 手机号脱敏显示"""

    __tablename__ = "leads"
    __table_args__ = (
        Index("uq_leads_external_source_id", "external_source", "external_id", unique=True),
        Index("idx_leads_attribution_time", "attribution_status", "create_time"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    # 外部客资可能在下播后才提交。找不到真实场次时先留空，进入“待归属”，
    # 绝不能为了满足非空约束随便猜一个场次。
    session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=True, comment="真实匹配的直播场次ID")
    lead_name = Column(String(100), nullable=True, comment="留资姓名")
    lead_phone = Column(String(20), nullable=True, comment="手机号")
    douyin_id = Column(String(100), nullable=True, comment="客户抖音号")
    anchor_name = Column(String(100), nullable=True, comment="客资提交时记录的主播")
    lead_source = Column(String(50), nullable=True, comment="业务来源：私信/小风车/表单/评论")
    external_source = Column(String(50), nullable=True, comment="外部数据系统标识")
    external_id = Column(BigInteger, nullable=True, comment="外部系统唯一编号")
    attribution_status = Column(
        String(20),
        nullable=False,
        default="matched",
        comment="场次归属状态：matched/pending",
    )
    is_valid = Column(Integer, default=1, comment="是否有效留资：1有效 0无效")
    remark = Column(String(500), nullable=True, comment="备注")
    create_time = Column(DateTime, nullable=True, comment="留资时间")
