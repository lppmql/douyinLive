"""
抖音留资直播分析系统 - FastAPI 入口
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logger import logger
from app.core.database import engine, Base
from app.api.v1 import v1_router
from app.services.collector.scheduler import scheduler_manager
from app.api.v1.ws import transcript_ws


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} 启动中...")
    logger.info(f"📦 数据库: {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}")
    logger.info(f"🔴 Redis: {settings.REDIS_URL}")

    try:
        with engine.connect() as conn:
            logger.info("✅ 数据库连接成功")
    except Exception as e:
        logger.warning(f"⚠️  数据库连接失败: {e}")

    # 自动启动监控调度器
    if settings.MONITOR_ENABLED:
        await scheduler_manager.start()
        logger.info("✅ 采集调度器已自动启动")
    else:
        logger.info("⏸️  采集调度器未启用 (MONITOR_ENABLED=false)")

    yield

    if scheduler_manager.running:
        await scheduler_manager.stop()
    logger.info("🛑 应用关闭")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# CORS 配置（允许前端跨域）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:9527", "http://127.0.0.1:9527"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


# 注册 API 路由
app.include_router(v1_router)
app.add_websocket_route("/ws/transcript/{session_id}", transcript_ws)
