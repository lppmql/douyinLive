"""Phase 1: 所有 CRUD API 路由注册 + Phase 3: 采集路由 + Phase 4: 监控路由"""
from fastapi import APIRouter

from app.api.v1.live_rooms import router as live_rooms_router
from app.api.v1.live_sessions import router as live_sessions_router
from app.api.v1.live_metrics import router as live_metrics_router
from app.api.v1.comments import router as comments_router
from app.api.v1.leads import router as leads_router
from app.api.v1.transcript_segments import router as transcript_segments_router
from app.api.v1.analysis_reports import router as analysis_reports_router
from app.api.v1.knowledge_base import router as knowledge_base_router
from app.api.v1.collector import router as collector_router
from app.api.v1.monitor import router as monitor_router
from app.api.v1.ws import rest_router as transcript_router

from app.api.v1.prompt_templates import router as prompt_templates_router
from app.api.v1.ai import router as ai_router
from app.api.v1.auth import router as auth_router
from app.api.v1.user_mgmt import router as user_mgmt_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.dataease import router as dataease_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(live_rooms_router)
v1_router.include_router(live_sessions_router)
v1_router.include_router(live_metrics_router)
v1_router.include_router(comments_router)
v1_router.include_router(leads_router)
v1_router.include_router(transcript_segments_router)
v1_router.include_router(analysis_reports_router)
v1_router.include_router(knowledge_base_router)
v1_router.include_router(collector_router)
v1_router.include_router(monitor_router)
v1_router.include_router(transcript_router)
v1_router.include_router(prompt_templates_router)
v1_router.include_router(ai_router)
v1_router.include_router(auth_router)
v1_router.include_router(user_mgmt_router)
v1_router.include_router(dashboard_router)
v1_router.include_router(dataease_router)

__all__ = ["v1_router"]
