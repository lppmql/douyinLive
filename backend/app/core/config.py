from pathlib import Path
from urllib.parse import urlparse
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录（config.py → app/core/ → backend/ → 项目根目录）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",  # 忽略 docker-compose / start.sh 用但 Python 不用的变量
    )

    # 应用
    APP_NAME: str = "零食店避坑直播运营复盘系统"
    APP_VERSION: str = "0.9.0"
    DEBUG: bool = False
    ALLOW_SYNTHETIC_DATA: bool = False
    LOG_FORMAT: str = "json"
    OBSERVABILITY_ENABLED: bool = True

    # 数据库
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "douyin_live"
    DATABASE_URL: str = ""
    DATABASE_ECHO: bool = False
    DATAEASE_READER_USER: str = "dataease_reader"
    DATAEASE_READER_PASSWORD: str = "dataease_reader_change_me"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    TASK_EVENT_STREAM: str = "douyin:task-events"
    TASK_EVENT_STREAM_MAXLEN: int = 10000
    TASK_HEARTBEAT_TIMEOUT_SECONDS: int = 180

    # DeepSeek
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_API_URL: str = "https://api.deepseek.com"

    # ASR 并发。旧固定值仅保留环境兼容，真实 Worker 使用资源自适应上限。
    MAX_REALTIME_ASR_TASKS: int = 1
    ASR_DYNAMIC_MAX_TASKS: int = 4
    ASR_WORKER_MODE: bool = False
    SAVE_AUDIO: bool = False
    SAVE_VIDEO: bool = False

    # Phase 5: FunASR
    FUNASR_HOST: str = "localhost"
    FUNASR_PORT: int = 10096
    FUNASR_WS_URL: str = "ws://localhost:10096"
    ASR_SAMPLE_RATE: int = 16000
    ASR_AUTO_START: bool = True
    ASR_MAX_QUEUED: int = 5
    ASR_ENGINE_READY_TIMEOUT_SECONDS: int = 300
    ASR_TASK_TIMEOUT_SECONDS: int = 600
    ASR_NO_AUDIO_TIMEOUT_SECONDS: int = 30
    ASR_CHUNK_SECONDS: int = 300
    ASR_CHUNK_MAX_RETRIES: int = 2
    ASR_ALLOW_MOCK: bool = False

    # P1: 知识库时间片
    KNOWLEDGE_SLICE_SECONDS: int = 300

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

    # 数据采集控制中心调度。0 表示自动同步一次处理全部待补齐场次。
    COLLECTOR_SERVICE_TICK_SECONDS: int = 10
    DATA_REFRESH_INTERVAL_SECONDS: int = 600
    AI_REVIEW_INTERVAL_SECONDS: int = 120
    KNOWLEDGE_SYNC_INTERVAL_SECONDS: int = 120
    DATAEASE_SYNC_INTERVAL_SECONDS: int = 30
    # 0 表示每次处理全部待同步场次；执行器仍逐场顺序写入，不会并发冲击 MySQL。
    CONTINUOUS_TASK_BATCH_SIZE: int = 0

    # 电脑资源保护。达到高压力后只延后新任务，不终止正在提交的数据。
    RESOURCE_SAMPLE_INTERVAL_SECONDS: int = 5
    RESOURCE_HIGH_CPU_PERCENT: int = 85
    RESOURCE_HIGH_MEMORY_PERCENT: int = 88
    RESOURCE_CRITICAL_MEMORY_PERCENT: int = 94
    RESOURCE_BACKOFF_MULTIPLIER: int = 3

    # Phase 8: JWT 认证
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 小时
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    # 原生图片、视频标签不能添加 Authorization 请求头，因此使用短时只读媒体 Cookie。
    MEDIA_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # 跨域与部署
    CORS_ORIGINS: str = "http://localhost:9527,http://127.0.0.1:9527"

    @property
    def db_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"

    @property
    def synthetic_data_enabled(self) -> bool:
        """模拟数据必须经过全局、调试模式和具体功能三重开关。"""
        return self.DEBUG and self.ALLOW_SYNTHETIC_DATA

    @property
    def monitor_mock_enabled(self) -> bool:
        return self.synthetic_data_enabled and self.MONITOR_MOCK_MODE

    @property
    def asr_mock_enabled(self) -> bool:
        return self.synthetic_data_enabled and self.ASR_ALLOW_MOCK

    @property
    def redacted_redis_url(self) -> str:
        """日志只显示 Redis 地址，不暴露账号和密码。"""
        parsed = urlparse(self.REDIS_URL)
        host = parsed.hostname or "unknown"
        port = f":{parsed.port}" if parsed.port else ""
        database = parsed.path or ""
        return f"{parsed.scheme or 'redis'}://{host}{port}{database}"

    def runtime_configuration_issues(self) -> tuple[list[str], list[str]]:
        """返回阻断启动的错误和不阻断本地开发的安全提醒。"""
        errors: list[str] = []
        warnings: list[str] = []
        if not self.DB_PASSWORD:
            errors.append("DATABASE_PASSWORD_MISSING")
        elif not self.DEBUG and len(self.DB_PASSWORD) < 16:
            errors.append("DATABASE_PASSWORD_INSECURE")
        if self.ASR_CHUNK_SECONDS < 30:
            errors.append("ASR_CHUNK_SECONDS_TOO_SMALL")
        if self.ASR_MAX_QUEUED < 1:
            errors.append("ASR_QUEUE_LIMIT_INVALID")
        if not 1 <= self.ASR_DYNAMIC_MAX_TASKS <= 16:
            errors.append("ASR_DYNAMIC_MAX_TASKS_INVALID")
        if self.MONITOR_CHECK_INTERVAL < 10:
            errors.append("MONITOR_INTERVAL_TOO_SMALL")
        if self.COLLECTOR_SERVICE_TICK_SECONDS < 5:
            errors.append("COLLECTOR_SERVICE_TICK_TOO_SMALL")
        if self.CONTINUOUS_TASK_BATCH_SIZE < 0:
            errors.append("CONTINUOUS_TASK_BATCH_INVALID")
        if not 50 <= self.RESOURCE_HIGH_MEMORY_PERCENT < self.RESOURCE_CRITICAL_MEMORY_PERCENT <= 99:
            errors.append("RESOURCE_MEMORY_THRESHOLD_INVALID")
        if not self.DEBUG and (
            len(self.JWT_SECRET_KEY) < 32
            or self.JWT_SECRET_KEY in {"replace-with-a-long-random-secret", "douyin-live-jwt-secret-change-in-prod"}
        ):
            errors.append("JWT_SECRET_INSECURE")
        if not 1 <= self.MEDIA_ACCESS_TOKEN_EXPIRE_MINUTES <= 120:
            errors.append("MEDIA_ACCESS_TOKEN_EXPIRE_INVALID")

        if self.DB_USER.lower() == "root":
            warnings.append("DATABASE_ROOT_USER")
        parsed_redis = urlparse(self.REDIS_URL)
        if not parsed_redis.password:
            warnings.append("REDIS_AUTH_DISABLED")
        if self.DATAEASE_READER_PASSWORD in {"", "dataease_reader_change_me", "请修改为仅供DataEase使用的强密码"}:
            warnings.append("DATAEASE_READER_PASSWORD_INSECURE")
        return errors, warnings

settings = Settings()
