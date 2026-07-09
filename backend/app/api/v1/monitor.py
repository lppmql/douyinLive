"""Phase 4: 直播监控管理 API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.models.live_rooms import LiveRoom
from app.schemas.monitor import (
    MonitorStatusResponse,
    MonitorRoomItem,
    MonitorActionResponse,
)
from app.services.collector.scheduler import scheduler_manager
from app.services.collector.monitor import MockLiveDetector

router = APIRouter(prefix="/monitor", tags=["直播监控"])


@router.get("/status", response_model=MonitorStatusResponse)
def get_monitor_status():
    """获取监控器状态"""
    return MonitorStatusResponse(
        enabled=settings.MONITOR_ENABLED,
        running=scheduler_manager.running,
        mock_mode=settings.MONITOR_MOCK_MODE,
        active_session_count=len(scheduler_manager.get_active_sessions()),
        active_sessions=scheduler_manager.get_active_sessions(),
    )


@router.post("/start", response_model=MonitorActionResponse)
async def start_monitor():
    """启动监控"""
    import asyncio
    await scheduler_manager.start()
    return MonitorActionResponse(success=True, message="监控已启动")


@router.post("/stop", response_model=MonitorActionResponse)
async def stop_monitor():
    """停止监控"""
    await scheduler_manager.stop()
    return MonitorActionResponse(success=True, message="监控已停止")


@router.get("/rooms", response_model=list[MonitorRoomItem])
def list_monitor_rooms(db: Session = Depends(get_db)):
    """获取所有直播间及监控状态"""
    rooms = db.query(LiveRoom).all()
    active = scheduler_manager.get_active_sessions()
    return [
        MonitorRoomItem(
            room_id=r.id,
            account_name=r.account_name,
            anchor_name=r.anchor_name,
            monitored=r.id in active,
        )
        for r in rooms
    ]


@router.post("/test/trigger-live", response_model=MonitorActionResponse)
async def trigger_live():
    """Mock 模式模拟开播事件"""
    if not settings.MONITOR_MOCK_MODE:
        raise HTTPException(400, "非 Mock 模式下不可用")
    detector = MockLiveDetector(idle_count=0, live_count=10)
    result = await detector.detect()
    if result.is_live:
        return MonitorActionResponse(success=True, message=f"模拟开播: {result.session_title}")
    return MonitorActionResponse(success=False, message="模拟开播失败")


@router.post("/test/trigger-end", response_model=MonitorActionResponse)
async def trigger_end():
    """Mock 模式模拟下播"""
    if not settings.MONITOR_MOCK_MODE:
        raise HTTPException(400, "非 Mock 模式下不可用")
    active = scheduler_manager.get_active_sessions()
    if not active:
        return MonitorActionResponse(success=False, message="无活跃场次")
    return MonitorActionResponse(success=True, message=f"已触发 {len(active)} 个场次下播")
