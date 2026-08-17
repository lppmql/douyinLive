"""知识库对话历史 — Pydantic schema（2026-07-28）"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ── 消息 ──


class ConversationMessageOut(BaseModel):
    """单条消息输出"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: str  # user / assistant
    content: str
    sources: list[dict] | None = None
    feedback: str | None = None  # like / dislike / null
    error: bool = False
    created_at: datetime | None = None

# ── 对话 ──


class ConversationListItem(BaseModel):
    """对话列表项（不含消息内容，只含摘要信息）"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str | None = None
    message_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

class ConversationDetail(BaseModel):
    """对话详情（含消息列表）"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str | None = None
    messages: list[ConversationMessageOut] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None

class ConversationCreateRequest(BaseModel):
    """新建对话请求 — 可带首条消息"""
    title: str | None = None
    first_message: str | None = Field(None, max_length=2000)


class ConversationDeleteResponse(BaseModel):
    """删除对话响应"""
    ok: bool = True
    deleted_id: int


# ── 反馈 ──


class FeedbackRequest(BaseModel):
    """消息反馈请求"""
    feedback: Literal["like", "dislike"]
