"""Phase 4: 监控管理 Pydantic Schema"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class MonitorStatusResponse(BaseModel):
    enabled: bool = False
    running: bool = False
    mock_mode: bool = False
    active_session_count: int = 0
    active_sessions: list[int] = []
    last_error: Optional[str] = None


class MonitorRoomItem(BaseModel):
    room_id: int
    account_name: Optional[str] = None
    anchor_name: Optional[str] = None
    monitored: bool = False


class MonitorActionResponse(BaseModel):
    success: bool = True
    message: str = ""
