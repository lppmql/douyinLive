"""AI 自动剪辑 API 数据模型。

响应模式与现有业务 API（如 collector.py）一致：直接返回业务模型，
不套 SoybeanResponse 包装（auth 相关接口才使用包装）。
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class ClipClipResponse(BaseModel):
    """单条成片（短视频成品）。"""

    id: int
    session_id: int
    clip_order: int
    status: str
    title: Optional[str] = None
    theme: Optional[str] = None
    description: Optional[str] = None
    topics: list[str] = []
    segments: list[dict[str, Any]] = []
    duration_seconds: Optional[int] = None
    video_path: Optional[str] = None
    cover_path: Optional[str] = None
    is_manual: int = 0
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ClipSessionOverview(BaseModel):
    """一场直播的剪辑总览（任务 + 成片列表）。"""

    session_id: int
    session_title: Optional[str] = None
    anchor_name: Optional[str] = None
    live_start_time: Optional[datetime] = None
    live_duration_seconds: Optional[int] = None
    detail_collection_status: Optional[str] = None
    task: Optional[dict[str, Any]] = None
    clips: list[ClipClipResponse] = []


class ClipGenerateRequest(BaseModel):
    """触发生成/重剪的请求体。"""

    user_hint: Optional[str] = None  # 人工指定的主题或时间范围要求（可空）


class ClipActionResponse(BaseModel):
    """任务操作统一响应。"""

    success: bool
    message: str
    task: Optional[dict[str, Any]] = None


class ClipTaskListResponse(BaseModel):
    """剪辑任务列表（分页）。"""

    total: int
    items: list[dict[str, Any]]
