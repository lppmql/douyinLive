"""AI 分析模块 — Pydantic 请求/响应模型"""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field


# ── 通用测试 ──

class AiTestOkResponse(BaseModel):
    status: str = "ok"
    reply: str


class AiTestErrorResponse(BaseModel):
    status: str = "error"
    message: str


class AiTestResponse(BaseModel):
    """POST /ai/test — 测试 DeepSeek 连通性"""
    status: str
    reply: str | None = None
    message: str | None = None


# ── 话术评分 ──

class AiScoreResponse(BaseModel):
    """POST /ai/score/{session_id}"""
    status: str
    result: dict[str, Any] | None = None


class AiPipelineResponse(BaseModel):
    """POST /ai/pipeline/{session_id}"""
    status: str
    result: dict[str, Any]
    live_data_saved: int = 0
    comments_saved: int = 0
    transcript_saved: int = 0
    analysis_saved: int = 0
    time_slices_created: int = 0
    time_slices_updated: int = 0
    time_slices_unchanged: int = 0
    time_slices_total: int = 0
    unmapped_comments: int = 0


class AiBatchScoreResponse(BaseModel):
    """POST /ai/score/batch"""
    status: str
    scored_count: int
    session_ids: list[int] = Field(default_factory=list)


# ── 趋势 / 异常 / 优化 ──

class AiTrendResponse(BaseModel):
    """POST /ai/trend"""
    status: str
    result: dict[str, Any] | None = None


class AiAnomalyResponse(BaseModel):
    """POST /ai/anomaly/{session_id}"""
    status: str
    result: dict[str, Any] | None = None


class AiOptimizeResponse(BaseModel):
    """POST /ai/optimize/{session_id}"""
    status: str
    result: dict[str, Any]


# ── 高意向用户 ──

class HighIntentUserOut(BaseModel):
    id: int
    session_id: int | None = None
    user_name: str | None = None
    phone: str | None = None
    product_interest: str | None = None
    intent_level: str | None = None
    intent_reason: str | None = None
    is_contacted: int | None = 0
    created_at: str | None = None


class AiHighIntentResponse(BaseModel):
    """POST /ai/high-intent/{session_id}"""
    status: str
    count: int = 0
    users: list[dict[str, Any]] = Field(default_factory=list)


# ── 知识库 ──

class AiQaResponse(BaseModel):
    """POST /ai/qa"""
    answer: str = ""
    sources: list[dict[str, Any]] = Field(default_factory=list)
    has_result: bool = False


class AiKbSaveResponse(BaseModel):
    """POST /ai/kb/save/{session_id}"""
    status: str
    live_data_saved: int = 0
    comments_saved: int = 0
    transcript_saved: int = 0
    analysis_saved: int = 0
    time_slices_created: int = 0
    time_slices_updated: int = 0
    time_slices_unchanged: int = 0
    time_slices_total: int = 0
    unmapped_comments: int = 0


class AiKbSyncRecentResponse(BaseModel):
    """POST /ai/kb/sync/recent"""
    status: str
    session_count: int = 0
    live_data_saved: int = 0
    comments_saved: int = 0
    transcript_saved: int = 0
    analysis_saved: int = 0
    time_slices_created: int = 0
    time_slices_updated: int = 0
    time_slices_unchanged: int = 0
    time_slices_total: int = 0
    unmapped_comments: int = 0
