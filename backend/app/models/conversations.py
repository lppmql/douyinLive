"""知识库对话历史表（2026-07-28 方案 C Chat UI 全面升级）

两张表：
- Conversation：一次对话会话（标题、时间）
- ConversationMessage：对话中的每条消息（用户问题 / AI 回答）
"""

from sqlalchemy import Column, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class Conversation(Base, TimestampMixin):
    """对话会话 — 相当于 ChatGPT 的一个对话线程"""

    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="对话ID")
    title = Column(String(200), nullable=True, comment="对话标题（自动取首条问题前50字）")
    message_count = Column(Integer, default=0, comment="消息条数（冗余字段，方便列表展示）")

    # 一对多：一个对话有多条消息
    messages = relationship(
        "ConversationMessage",
        back_populates="conversation",
        order_by="ConversationMessage.id",
        cascade="all, delete-orphan",
    )


class ConversationMessage(Base, TimestampMixin):
    """对话消息 — 对话中每一条用户/助手消息"""

    __tablename__ = "conversation_messages"
    __table_args__ = (Index("ix_conversation_messages_conv_id", "conversation_id", "id"),)

    id = Column(Integer, primary_key=True, autoincrement=True, comment="消息ID")
    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属对话ID",
    )
    role = Column(String(20), nullable=False, comment="角色：user / assistant")
    content = Column(Text, nullable=False, comment="消息内容")
    sources = Column(JSON, nullable=True, comment="引用来源列表（仅 assistant 消息）")
    feedback = Column(String(10), nullable=True, comment="用户反馈：like / dislike / null")
    error = Column(Integer, default=0, comment="是否错误消息：0=正常 1=出错")

    # 反向引用
    conversation = relationship("Conversation", back_populates="messages")
