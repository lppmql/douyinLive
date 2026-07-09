"""Phase 1: 所有 CRUD API 路由注册"""
from fastapi import APIRouter

from app.api.v1.live_rooms import router as live_rooms_router
from app.api.v1.live_sessions import router as live_sessions_router
from app.api.v1.live_metrics import router as live_metrics_router
from app.api.v1.comments import router as comments_router
from app.api.v1.leads import router as leads_router
from app.api.v1.transcript_segments import router as transcript_segments_router
from app.api.v1.analysis_reports import router as analysis_reports_router
from app.api.v1.knowledge_base import router as knowledge_base_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(live_rooms_router)
v1_router.include_router(live_sessions_router)
v1_router.include_router(live_metrics_router)
v1_router.include_router(comments_router)
v1_router.include_router(leads_router)
v1_router.include_router(transcript_segments_router)
v1_router.include_router(analysis_reports_router)
v1_router.include_router(knowledge_base_router)

__all__ = ["v1_router"]
