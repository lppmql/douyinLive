"""采集器共享常量 — URL / 配置 / 指纹

避免在多个模块中重复定义相同的 URL 和配置项。
"""

# ── 抖音企业号后台地址 ──
LEADS_BASE = "https://leads.cluerich.com"
LIVE_SCREEN_URL = f"{LEADS_BASE}/pc/analysis/live-screen"
COMMENT_URL = f"{LEADS_BASE}/pc/analysis/live-comment"

# ── 统一浏览器指纹参数（登录 + 采集用同一套）──
DEFAULT_FINGERPRINT = {
    "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "viewport": {"width": 1920, "height": 1080},
    "locale": "zh-CN",
    "timezone_id": "Asia/Shanghai",
    "device_scale_factor": 1,
    "color_scheme": "light",
}
