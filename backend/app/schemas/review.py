"""直播复盘工作台请求模型。"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ReviewActionCreate(BaseModel):
    finding_id: int | None = None
    title: str = Field(min_length=2, max_length=200)
    description: str | None = None
    owner_name: str | None = Field(default=None, max_length=100)
    priority: Literal["low", "medium", "high"] = "medium"
    due_at: datetime | None = None


class ReviewActionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None
    owner_name: str | None = Field(default=None, max_length=100)
    priority: Literal["low", "medium", "high"] | None = None
    status: Literal["pending", "in_progress", "completed", "verified"] | None = None
    due_at: datetime | None = None
    verification_session_id: int | None = None
    verification_note: str | None = None


class FindingStatusUpdate(BaseModel):
    status: Literal["open", "confirmed", "dismissed", "resolved"]


class ScriptAssetCreate(BaseModel):
    transcript_segment_id: int | None = None
    category: str = Field(min_length=2, max_length=40)
    title: str = Field(min_length=2, max_length=200)
    content: str = Field(min_length=2)
    start_seconds: float | None = Field(default=None, ge=0)
    end_seconds: float | None = Field(default=None, ge=0)
    performance_note: str | None = None
    status: Literal["candidate", "approved", "archived"] = "candidate"


class ScriptAssetUpdate(BaseModel):
    category: str | None = Field(default=None, min_length=2, max_length=40)
    title: str | None = Field(default=None, min_length=2, max_length=200)
    performance_note: str | None = None
    status: Literal["candidate", "approved", "archived"] | None = None


# ── 响应模型 ──

from typing import Any

class ReviewWorkbenchResponse(BaseModel):
    """GET /reviews/{session_id}/workbench — 复盘工作台"""
    session_id: int | None = None
    anchor_name: str | None = None
    session_title: str | None = None
    business_context: str | None = None
    completeness: dict[str, Any] = Field(default_factory=dict)
    transcript_segments: list[dict[str, Any]] = Field(default_factory=list)
    domain_coverage: list[dict[str, Any]] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    score: dict[str, Any] | None = None
    actions: list[dict[str, Any]] = Field(default_factory=list)
    assets: list[dict[str, Any]] = Field(default_factory=list)
    script_assets: list[dict[str, Any]] = Field(default_factory=list)
    live_alerts: list[dict[str, Any]] = Field(default_factory=list)
    latest_reports: list[dict[str, Any]] = Field(default_factory=list)


class ReviewGenerateResponse(BaseModel):
    """POST /reviews/{session_id}/generate"""
    status: str
    finding_count: int = 0
    workbench: dict[str, Any] = Field(default_factory=dict)


class ReviewComparisonResponse(BaseModel):
    """GET /reviews/{session_id}/comparison"""
    primary: dict[str, Any] = Field(default_factory=dict)
    baseline: dict[str, Any] = Field(default_factory=dict)


class ReviewFindingOut(BaseModel):
    """PATCH /reviews/{session_id}/findings/{finding_id}"""
    id: int | None = None
    session_id: int | None = None
    status: str | None = None
    category: str | None = None
    title: str | None = None
    confidence: float | None = None
    start_seconds: float | None = None
    end_seconds: float | None = None
    evidence_summary: str | None = None
    recommendation: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ReviewActionOut(BaseModel):
    """POST/PATCH /reviews/{session_id}/actions"""
    id: int | None = None
    session_id: int | None = None
    finding_id: int | None = None
    title: str | None = None
    description: str | None = None
    owner_name: str | None = None
    priority: str | None = None
    status: str | None = None
    due_at: str | None = None
    verification_session_id: int | None = None
    verification_note: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ReviewScriptAssetOut(BaseModel):
    """POST/PATCH /reviews/{session_id}/script-assets"""
    id: int | None = None
    session_id: int | None = None
    transcript_segment_id: int | None = None
    category: str | None = None
    title: str | None = None
    content: str | None = None
    start_seconds: float | None = None
    end_seconds: float | None = None
    performance_note: str | None = None
    status: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ComplianceRuleOut(BaseModel):
    """GET /reviews/compliance/rules"""
    id: int | None = None
    category: str | None = None
    title: str | None = None
    description: str | None = None
    enabled: int | None = None
    created_at: str | None = None
