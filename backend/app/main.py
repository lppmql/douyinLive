"""
抖音留资直播分析系统 - FastAPI 入口
"""
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logger import logger
from app.core.database import engine, SessionLocal
from app.models.scraper_tasks import ScraperTask
from app.api.v1 import v1_router
from app.services.collector.scheduler import scheduler_manager
from app.api.v1.ws import transcript_ws


def recover_interrupted_collector_tasks() -> int:
    """进程重启后关闭无法继续执行的遗留采集任务。"""
    db = SessionLocal()
    try:
        tasks = db.query(ScraperTask).filter(ScraperTask.status == "running").all()
        for task in tasks:
            task.status = "failed"
            task.completed_at = datetime.utcnow()
            task.error_message = "后端服务重启，任务已中断，请重新执行"
            task.progress_stage = "interrupted"
            task.progress_message = "任务因服务重启而中断"
        if tasks:
            db.commit()
        return len(tasks)
    finally:
        db.close()


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

    try:
        recovered_tasks = recover_interrupted_collector_tasks()
        if recovered_tasks:
            logger.warning("已回收 %s 个服务重启前遗留的采集任务", recovered_tasks)
    except Exception as exc:
        logger.warning("遗留采集任务恢复失败，不阻塞服务启动: %s", exc)

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
    allow_origins=["http://localhost:9527", "http://127.0.0.1:9527"],
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
    database_ok = False
    redis_ok = False
    try:
        from sqlalchemy import text

        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        database_ok = True
    except Exception:
        pass

    try:
        from redis import Redis

        redis_client = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
        redis_ok = bool(redis_client.ping())
        redis_client.close()
    except Exception:
        pass

    healthy = database_ok and redis_ok
    return {
        "status": "ok" if healthy else "degraded",
        "database": "ok" if database_ok else "error",
        "redis": "ok" if redis_ok else "error",
        "monitor": "running" if scheduler_manager.running else "stopped",
    }


# 注册 API 路由
app.include_router(v1_router)
app.add_websocket_route("/ws/transcript/{session_id}", transcript_ws)
