import os
from pathlib import Path
from pydantic_settings import BaseSettings

# 项目根目录（config.py → app/core/ → backend/ → 项目根目录）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class Settings(BaseSettings):
    # 应用
    APP_NAME: str = "抖音留资直播分析系统"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    # 数据库
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "root123"
    DB_NAME: str = "douyin_live"
    DATABASE_URL: str = ""

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # DeepSeek
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_API_URL: str = "https://api.deepseek.com"

    # ASR 并发
    MAX_REALTIME_ASR_TASKS: int = 1
    ASR_WORKER_MODE: bool = False
    SAVE_AUDIO: bool = False
    SAVE_VIDEO: bool = False

    # Phase 5: FunASR
    FUNASR_HOST: str = "localhost"
    FUNASR_PORT: int = 10096
    FUNASR_WS_URL: str = "ws://localhost:10096"
    ASR_SAMPLE_RATE: int = 16000
    ASR_MAX_QUEUED: int = 5
    ASR_TASK_TIMEOUT_SECONDS: int = 600

    # Playwright / 采集
    PLAYWRIGHT_HEADLESS: bool = True
    ROOM_COLLECTION_TIMEOUT_SECONDS: int = 90

    # Phase 4: 直播采集监控
    MONITOR_ENABLED: bool = False
    MONITOR_MOCK_MODE: bool = False
    MONITOR_CHECK_INTERVAL: int = 120
    METRICS_COLLECT_INTERVAL: int = 30
    COMMENT_COLLECT_INTERVAL: int = 60
    PROFILE_COLLECT_INTERVAL: int = 120

    # Phase 8: JWT 认证
    JWT_SECRET_KEY: str = "douyin-live-jwt-secret-change-in-prod"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 小时
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    @property
    def db_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"

    class Config:
        env_file = str(PROJECT_ROOT / ".env")
        env_file_encoding = "utf-8"


settings = Settings()
