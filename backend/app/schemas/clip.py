"""AI 自动剪辑 API 数据模型。

响应模式与现有业务 API（如 collector.py）一致：直接返回业务模型，
不套 SoybeanResponse 包装（auth 相关接口才使用包装）。
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ClipClipResponse(BaseModel):
    """单条成片（短视频成品）。"""

    id: int
    session_id: int
    clip_order: int
    status: str
    title: Optional[str] = None
    theme: Optional[str] = None
    description: Optional[str] = None
    topics: list[str] = Field(default_factory=list)
    segments: list[dict[str, Any]] = Field(default_factory=list)
    duration_seconds: Optional[int] = None
    video_path: Optional[str] = None
    cover_path: Optional[str] = None
    subtitle_path: Optional[str] = None
    subtitle_srt_path: Optional[str] = None
    subtitle_precision: str = "segment_estimated"
    render_version: int = 1
    can_rerender_subtitle: bool = False
    artifact_versions: list[dict[str, Any]] = Field(default_factory=list)
    selection_evidence: dict[str, Any] = Field(default_factory=dict)
    qc: dict[str, Any] = Field(default_factory=dict)
    is_manual: int = 0
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ClipSessionOverview(BaseModel):
    """一场直播的剪辑总览（任务 + 成片列表）。"""

    session_id: int
    session_title: Optional[str] = None
    anchor_name: Optional[str] = None
    anchor_nickname: Optional[str] = None
    anchor_avatar_url: Optional[str] = None
    douyin_id: Optional[str] = None
    live_start_time: Optional[datetime] = None
    live_duration_seconds: Optional[int] = None
    detail_collection_status: Optional[str] = None
    task: Optional[dict[str, Any]] = None
    clips: list[ClipClipResponse] = Field(default_factory=list)


class ClipGenerateRequest(BaseModel):
    """触发生成/重剪的请求体。"""

    user_hint: Optional[str] = None  # 人工指定的主题或时间范围要求（可空）


class ClipSubtitleSegment(BaseModel):
    """人工校正的一段字幕；起止时间必须仍在原选段范围内。"""

    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = Field(min_length=1, max_length=5000)


class ClipSubtitleRerenderRequest(BaseModel):
    """仅重制字幕；不传 segments 时按数据库中的精确时间自动重制。"""

    segments: list[ClipSubtitleSegment] | None = Field(
        default=None, min_length=1, max_length=3
    )


class ClipActionResponse(BaseModel):
    """任务操作统一响应。"""

    success: bool
    message: str
    task: Optional[dict[str, Any]] = None


class ClipTaskListResponse(BaseModel):
    """剪辑任务列表（分页）。"""

    total: int
    items: list[dict[str, Any]]
