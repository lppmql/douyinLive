"""
零食店避坑直播运营复盘系统 - FastAPI 入口
"""
import time
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logger import logger
from app.core.database import engine, SessionLocal
from app.core.error_handler import register_exception_handlers
from app.models.scraper_tasks import ScraperTask
from app.api.v1 import v1_router
from app.api.v1.auth import router as auth_router
from app.api.v1.live_sessions import stream_router  # 浏览器回放流端点，无需鉴权
from app.services.collector.scheduler import scheduler_manager
from app.services.tasks.runtime import publish_task_event, touch_task
from app.services.tasks.control import CONTROL_TASK_TYPES, collector_task_control
from app.services.tasks.module_service import collector_module_service
from app.services.ai.seed_prompts import seed_prompts
from app.api.v1.ws import transcript_ws
from app.core.observability import (
    new_trace_id,
    observe_http,
    refresh_runtime_metrics,
    trace_id_var,
)
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from app.core.status import TaskStatus


def recover_interrupted_collector_tasks() -> int:
    """进程重启后关闭无法继续执行的遗留采集任务。"""
    db = SessionLocal()
    try:
        tasks = db.query(ScraperTask).filter(
            ScraperTask.status == TaskStatus.RUNNING,
            ~ScraperTask.task_type.in_(CONTROL_TASK_TYPES),
        ).all()
        for task in tasks:
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.utcnow()
            task.error_message = "后端服务重启，任务已中断，请重新执行"
            task.progress_stage = "interrupted"
            task.progress_message = "任务因服务重启而中断"
            touch_task(task)
        if tasks:
            db.commit()
            for task in tasks:
                publish_task_event("scraper", task, "interrupted", {"reason": task.error_message})
        return len(tasks)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    configuration_errors, configuration_warnings = settings.runtime_configuration_issues()
    for warning in configuration_warnings:
        logger.warning("配置安全提醒 code=%s，请运行 make doctor 查看处理建议", warning)
    if configuration_errors:
        raise RuntimeError(f"启动配置校验失败: {', '.join(configuration_errors)}")

    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} 启动中...")
    logger.info(f"📦 数据库: {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}")
    logger.info(f"🔴 Redis: {settings.redacted_redis_url}")

    try:
        with engine.connect():
            logger.info("✅ 数据库连接成功")
    except Exception as e:
        logger.warning(f"⚠️  数据库连接失败: {e}")

    try:
        db = SessionLocal()
        seed_prompts(db)
    except Exception as exc:
        logger.warning("默认 AI 提示词检查失败，不阻塞服务启动: %s", exc)
    finally:
        if "db" in locals():
            db.close()

    try:
        requeued_tasks = collector_task_control.recover_interrupted_tasks()
        if requeued_tasks:
            logger.warning("已重新排队 %s 个可断点执行的控制任务", requeued_tasks)
        recovered_tasks = recover_interrupted_collector_tasks()
        if recovered_tasks:
            logger.warning("已回收 %s 个服务重启前遗留的采集任务", recovered_tasks)
    except Exception as exc:
        logger.warning("遗留采集任务恢复失败，不阻塞服务启动: %s", exc)

    await collector_task_control.start()
    await collector_module_service.start()
    logger.info("✅ 数据采集控制中心已恢复监控、ASR 与后台自动同步状态")

    yield

    # 先关掉所有“任务生产者”，再等待控制任务和实时页面完成，避免停机期间又创建浏览器。
    await collector_module_service.stop_scheduling()
    scheduler_manager.pause_scheduling()
    await collector_task_control.stop()
    await scheduler_manager.stop()
    await collector_module_service.release_runtime_resources()
    logger.info("🛑 应用关闭")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# CORS 配置（允许前端跨域）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.CORS_ORIGINS.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✨ 统一异常处理：把 FastAPI 默认的 {"detail":"..."} 转成前端认识的 {"code":"XXXX","msg":"..."}
register_exception_handlers(app)


@app.middleware("http")
async def trace_and_metrics_middleware(request: Request, call_next):
    trace_id = new_trace_id(request.headers.get("x-trace-id"))
    token = trace_id_var.set(trace_id)
    started_at = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Trace-ID"] = trace_id
        return response
    finally:
        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)
        if settings.OBSERVABILITY_ENABLED:
            observe_http(request.method, route_path, status_code, started_at)
        trace_id_var.reset(token)


@app.get("/")
def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": TaskStatus.RUNNING,
    }


@app.get("/health")
def health():
    configuration_errors, configuration_warnings = settings.runtime_configuration_issues()
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
        "monitor": TaskStatus.RUNNING if scheduler_manager.running else "stopped",
        "configuration": "error" if configuration_errors else "warning" if configuration_warnings else "ok",
        "configuration_issues": configuration_errors + configuration_warnings,
    }


@app.get("/metrics", include_in_schema=False)
def prometheus_metrics():
    """Prometheus 拉取入口。"""
    if not settings.OBSERVABILITY_ENABLED:
        return Response(status_code=404)
    db = SessionLocal()
    try:
        refresh_runtime_metrics(db, scheduler_manager.running)
    finally:
        db.close()
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# 注册 API 路由
# auth_router 单独注册（含公开的 login/refreshToken，不经过 v1_router 的全局鉴权）
app.include_router(auth_router, prefix="/api/v1")
# 浏览器 <video> 标签发请求时无法带 JWT header，回放流不经过 v1_router 全局鉴权
app.include_router(stream_router, prefix="/api/v1")
app.include_router(v1_router)
app.add_websocket_route("/ws/transcript/{session_id}", transcript_ws)
