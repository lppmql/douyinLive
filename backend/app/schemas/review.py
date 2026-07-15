"""直播复盘工作台请求模型。"""

from datetime import datetime
from typing import Literal

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
