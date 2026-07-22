"""业务 API 路由注册。

v1_router 统一要求登录鉴权（auth 路由因含 public 接口单独注册到 app）。
"""
from fastapi import APIRouter, Depends

from app.core.security import get_current_user
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
from app.api.v1.user_mgmt import router as user_mgmt_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.dataease import router as dataease_router
from app.api.v1.reviews import router as reviews_router
from app.api.v1.anchor_schedules import router as anchor_schedules_router

# 所有业务 API 统一要求登录（auth 路由含 login/refreshToken 公开接口，单独注册）
v1_router = APIRouter(prefix="/api/v1", dependencies=[Depends(get_current_user)])
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
v1_router.include_router(user_mgmt_router)
v1_router.include_router(dashboard_router)
v1_router.include_router(dataease_router)
v1_router.include_router(reviews_router)
v1_router.include_router(anchor_schedules_router)

__all__ = ["v1_router"]
