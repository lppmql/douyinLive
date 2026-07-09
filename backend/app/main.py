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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时检查数据库连接"""
    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} 启动中...")
    logger.info(f"📦 数据库: {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}")
    logger.info(f"🔴 Redis: {settings.REDIS_URL}")

    # 尝试连接数据库（建表在 Phase 1 进行）
    try:
        with engine.connect() as conn:
            logger.info("✅ 数据库连接成功")
    except Exception as e:
        logger.warning(f"⚠️  数据库连接失败: {e}")
        logger.warning("请确保 MySQL 已启动，可按 docker-compose.yml 配置")

    yield

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
