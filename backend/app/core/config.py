from pathlib import Path
from urllib.parse import urlparse
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录（config.py → app/core/ → backend/ → 项目根目录）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def is_local_ollama_url(value: str) -> bool:
    """只接受无认证信息、无重定向参数的本机 OpenAI 兼容地址。"""
    try:
        parsed = urlparse(value)
        return (
            parsed.scheme == "http"
            and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
            and parsed.path.rstrip("/") == "/v1"
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and (parsed.port is None or 1 <= parsed.port <= 65535)
        )
    except ValueError:
        return False


def is_valid_kezi_api_key(value: str) -> bool:
    """外部请求头密钥必须是无空格 ASCII，中文占位词不能冒充真实配置。"""
    return (
        len(value) >= 32
        and value.isascii()
        and value.isprintable()
        and not any(char.isspace() for char in value)
    )


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

    # 数据库
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    # 管理员密码只供首次建库和创建受限账号使用，业务进程不得使用 root。
    MYSQL_ROOT_PASSWORD: str = ""
    DB_USER: str = "douyin_app"
    DB_PASSWORD: str = ""
    DB_NAME: str = "douyin_live"
    DATABASE_URL: str = ""
    DATABASE_ECHO: bool = False

    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    TASK_EVENT_STREAM: str = "douyin:task-events"
    TASK_EVENT_STREAM_MAXLEN: int = 10000
    TASK_HEARTBEAT_TIMEOUT_SECONDS: int = 180

    # 本地 Ollama 大模型。只允许回环地址，避免把未鉴权的模型接口暴露到局域网。
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434/v1"
    OLLAMA_MODEL: str = "douyin-live-qwen"
    # 长场话术和剪辑选段可能使用 4 万以上 Token；本地模型需要更长超时。
    OLLAMA_REQUEST_TIMEOUT_SECONDS: int = 900

    # ASR 并发。旧固定值仅保留环境兼容，真实 Worker 使用资源自适应上限。
    MAX_REALTIME_ASR_TASKS: int = 1
    ASR_DYNAMIC_MAX_TASKS: int = 2
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
    # FunASR 容器崩溃后可能需要重新校验或加载 1.6GB 模型，低内存电脑预留 15 分钟。
    ASR_ENGINE_READY_TIMEOUT_SECONDS: int = 900
    ASR_TASK_TIMEOUT_SECONDS: int = 600
    ASR_NO_AUDIO_TIMEOUT_SECONDS: int = 30
    # 每 2 分钟形成一个可恢复检查点，避免长直播一直占住 ffmpeg 和识别资源。
    ASR_CHUNK_SECONDS: int = 120
    ASR_CHUNK_MAX_RETRIES: int = 2
    # 单模型分时：连续多少个直播分片后，让最新下播终稿推进一个分片。
    ASR_LIVE_CHUNK_QUOTA: int = 3
    # 直播音频独立落盘，避免 FunASR 处理离线终稿时漏掉正在直播的声音。
    ASR_AUDIO_BUFFER_ENABLED: bool = True
    ASR_AUDIO_BUFFER_RETENTION_HOURS: int = 24
    ASR_AUDIO_BUFFER_MAX_GB: float = 2.0
    # 60ms 音频帧每 50ms 发送，直播初稿约 1.2 倍速追赶；过快会挤爆在线模型。
    ASR_ONLINE_FRAME_INTERVAL_SECONDS: float = 0.05
    ASR_ONLINE_RESULT_TIMEOUT_SECONDS: int = 3
    ASR_COMPLETENESS_REPAIR_ROUNDS: int = 3
    ASR_ALLOW_MOCK: bool = False

    # P1: 知识库时间片
    KNOWLEDGE_SLICE_SECONDS: int = 300

    # Phase 36: Qdrant 向量数据库（知识库 RAG 语义检索）
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION_KB: str = "douyin_live_knowledge"
    QDRANT_COLLECTION_SLICES: str = "douyin_live_time_slices"
    HF_ENDPOINT: str = "https://hf-mirror.com"  # HuggingFace 镜像（国内下载模型用）

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

    # 评论用户公开资料补全使用独立 Cookie 与固定浏览器指纹，不复用企业后台采集账号。
    DOUYIN_PROFILE_COOKIE_FILE: str = "data/private/douyin_profile_cookie.txt"
    DOUYIN_PROFILE_USER_AGENT: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
    DOUYIN_PROFILE_SEC_CH_UA: str = (
        '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"'
    )
    DOUYIN_PROFILE_PLATFORM: str = "macOS"
    DOUYIN_PROFILE_LOCALE: str = "zh-CN"
    DOUYIN_PROFILE_TIMEZONE: str = "Asia/Shanghai"
    DOUYIN_PROFILE_VIEWPORT_WIDTH: int = 1920
    DOUYIN_PROFILE_VIEWPORT_HEIGHT: int = 1080
    DOUYIN_PROFILE_REQUEST_INTERVAL_SECONDS: float = 1.5
    DOUYIN_PROFILE_BATCH_SIZE: int = 30
    DOUYIN_PROFILE_BATCH_PAUSE_SECONDS: float = 10
    DOUYIN_PROFILE_CACHE_DAYS: int = 30
    DOUYIN_PROFILE_REQUEST_TIMEOUT_SECONDS: int = 20

    # 数据采集控制中心调度。0 表示自动同步一次处理全部待补齐场次。
    COLLECTOR_SERVICE_TICK_SECONDS: int = 10
    DATA_REFRESH_INTERVAL_SECONDS: int = 600
    AI_REVIEW_INTERVAL_SECONDS: int = 120
    KNOWLEDGE_SYNC_INTERVAL_SECONDS: int = 120
    # 客资查询密钥只放后端根目录 .env；前端只看到同步后的脱敏业务数据。
    KEZI_BASE_URL: str = "https://kezi.lpp6.com"
    KEZI_API_KEY: str = ""
    KEZI_SYNC_INTERVAL_SECONDS: int = 60
    KEZI_SYNC_PAGE_SIZE: int = 100
    KEZI_REQUEST_TIMEOUT_SECONDS: int = 15
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
    # ASR Worker 调用后端刷新流地址时使用。留空时从 JWT 密钥安全派生，避免公开接口。
    INTERNAL_WORKER_TOKEN: str = ""

    # 腾讯云短信。密钥只放根目录 .env，代码和日志都不能输出。
    TENCENT_SMS_APP_ID: str = ""
    TENCENT_SMS_APP_KEY: str = ""
    TENCENT_SMS_SIGN: str = ""
    TENCENT_SMS_TEMPLATE_CODE: str = ""
    SMS_CODE_EXPIRE_MINUTES: int = 5
    SMS_CODE_REDIS_PREFIX: str = "sms_code:"
    # 只在全新数据库没有任何用户时使用；创建成功后仍建议从用户管理页更换密码。
    BOOTSTRAP_ADMIN_USERNAME: str = ""
    BOOTSTRAP_ADMIN_PASSWORD: str = ""

    # AI 自动剪辑。回放与成片统一存 data/videos/<session_id>/ 下（data/ 已被 .gitignore 覆盖）。
    CLIP_STORAGE_DIR: str = "data/videos"
    # ffmpeg 重编码并发上限：剪辑是 CPU/GPU 重活，默认单并发避免拖垮直播采集。
    CLIP_MAX_CONCURRENT: int = 1
    # 可选：带 libass 的 ffmpeg 路径；Settings 会直接读取根目录 .env。
    CLIP_FFMPEG_BIN: str = ""
    # 竖屏成片目标分辨率（抖音主流 9:16）
    CLIP_TARGET_WIDTH: int = 1080
    CLIP_TARGET_HEIGHT: int = 1920
    # 回放下载超时（秒）：2 小时直播流拷贝到本地一般几分钟，30 分钟兜底。
    CLIP_REPLAY_DOWNLOAD_TIMEOUT_SECONDS: int = 1800
    # 回放源地址可能过期，默认只做容量告警；确认已有可靠归档后才能显式开启自动清理。
    CLIP_REPLAY_AUTO_DELETE: bool = False
    CLIP_REPLAY_RETENTION_DAYS: int = 14
    CLIP_REPLAY_MAX_GB: float = 20.0
    # 估算时间轴容易出现字幕提前/滞后，默认禁止确认成可发布成片。
    CLIP_ALLOW_ESTIMATED_SUBTITLE_APPROVAL: bool = False
    # 剪辑只允许运营在页面人工触发，离线终稿完成不再自动创建 AI 任务。

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
        elif not self.DEBUG and len(self.DB_PASSWORD) < 7:
            errors.append("DATABASE_PASSWORD_INSECURE")
        if self.ASR_CHUNK_SECONDS < 30:
            errors.append("ASR_CHUNK_SECONDS_TOO_SMALL")
        if self.ASR_MAX_QUEUED < 1:
            errors.append("ASR_QUEUE_LIMIT_INVALID")
        if not 1 <= self.ASR_LIVE_CHUNK_QUOTA <= 10:
            errors.append("ASR_LIVE_CHUNK_QUOTA_INVALID")
        if not 1 <= self.ASR_AUDIO_BUFFER_RETENTION_HOURS <= 168:
            errors.append("ASR_AUDIO_BUFFER_RETENTION_INVALID")
        if not 0.25 <= self.ASR_AUDIO_BUFFER_MAX_GB <= 20:
            errors.append("ASR_AUDIO_BUFFER_CAPACITY_INVALID")
        if not 0.04 <= self.ASR_ONLINE_FRAME_INTERVAL_SECONDS <= 0.06:
            errors.append("ASR_ONLINE_FRAME_INTERVAL_INVALID")
        if not 1 <= self.ASR_ONLINE_RESULT_TIMEOUT_SECONDS <= 15:
            errors.append("ASR_ONLINE_RESULT_TIMEOUT_INVALID")
        if not 1 <= self.ASR_COMPLETENESS_REPAIR_ROUNDS <= 10:
            errors.append("ASR_COMPLETENESS_REPAIR_ROUNDS_INVALID")
        if not 2 <= self.ASR_DYNAMIC_MAX_TASKS <= 16:
            errors.append("ASR_DYNAMIC_MAX_TASKS_INVALID")
        if self.MONITOR_CHECK_INTERVAL < 10:
            errors.append("MONITOR_INTERVAL_TOO_SMALL")
        if self.COLLECTOR_SERVICE_TICK_SECONDS < 5:
            errors.append("COLLECTOR_SERVICE_TICK_TOO_SMALL")
        if not 0.5 <= self.DOUYIN_PROFILE_REQUEST_INTERVAL_SECONDS <= 30:
            errors.append("DOUYIN_PROFILE_INTERVAL_INVALID")
        if not 1 <= self.DOUYIN_PROFILE_BATCH_SIZE <= 100:
            errors.append("DOUYIN_PROFILE_BATCH_SIZE_INVALID")
        if not 0 <= self.DOUYIN_PROFILE_BATCH_PAUSE_SECONDS <= 300:
            errors.append("DOUYIN_PROFILE_BATCH_PAUSE_INVALID")
        if not 1 <= self.DOUYIN_PROFILE_CACHE_DAYS <= 365:
            errors.append("DOUYIN_PROFILE_CACHE_DAYS_INVALID")
        if self.CONTINUOUS_TASK_BATCH_SIZE < 0:
            errors.append("CONTINUOUS_TASK_BATCH_INVALID")
        if not is_local_ollama_url(self.OLLAMA_BASE_URL):
            errors.append("OLLAMA_BASE_URL_NOT_LOCAL")
        if not self.OLLAMA_MODEL.strip():
            errors.append("OLLAMA_MODEL_MISSING")
        if not 30 <= self.OLLAMA_REQUEST_TIMEOUT_SECONDS <= 3600:
            errors.append("OLLAMA_TIMEOUT_INVALID")
        if not 1 <= self.CLIP_REPLAY_RETENTION_DAYS <= 365:
            errors.append("CLIP_REPLAY_RETENTION_INVALID")
        if not 1 <= self.CLIP_REPLAY_MAX_GB <= 1000:
            errors.append("CLIP_REPLAY_CAPACITY_INVALID")
        if not 10 <= self.KEZI_SYNC_INTERVAL_SECONDS <= 3600:
            errors.append("KEZI_SYNC_INTERVAL_INVALID")
        if not 1 <= self.KEZI_SYNC_PAGE_SIZE <= 500:
            errors.append("KEZI_SYNC_PAGE_SIZE_INVALID")
        if self.KEZI_API_KEY and not is_valid_kezi_api_key(self.KEZI_API_KEY):
            # 客资接入是可选模块：无效密钥只关闭该模块，不阻断直播、复盘等主功能。
            warnings.append("KEZI_API_KEY_INSECURE")
        if (
            not 50
            <= self.RESOURCE_HIGH_MEMORY_PERCENT
            < self.RESOURCE_CRITICAL_MEMORY_PERCENT
            <= 99
        ):
            errors.append("RESOURCE_MEMORY_THRESHOLD_INVALID")
        if not self.DEBUG and (
            len(self.JWT_SECRET_KEY) < 32
            or self.JWT_SECRET_KEY
            in {
                "replace-with-a-long-random-secret",
                "douyin-live-jwt-secret-change-in-prod",
            }
        ):
            errors.append("JWT_SECRET_INSECURE")
        if not 1 <= self.MEDIA_ACCESS_TOKEN_EXPIRE_MINUTES <= 120:
            errors.append("MEDIA_ACCESS_TOKEN_EXPIRE_INVALID")
        if not 1 <= self.SMS_CODE_EXPIRE_MINUTES <= 10:
            errors.append("SMS_CODE_EXPIRE_INVALID")

        if self.DB_USER.lower() == "root":
            warnings.append("DATABASE_ROOT_USER")
        parsed_redis = urlparse(self.REDIS_URL)
        if not parsed_redis.password:
            warnings.append("REDIS_AUTH_DISABLED")
        return errors, warnings


settings = Settings()
