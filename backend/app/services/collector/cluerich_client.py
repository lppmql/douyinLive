"""
Cluerich 直播后台采集客户端

封装 Cluerich 平台的特定采集逻辑，基于自适应采集框架。
使用正确的 cluerich URL 路径。
"""
from sqlalchemy.orm import Session
from playwright.async_api import BrowserContext

from app.services.collector.collector_framework import AdaptiveCollector
from app.models.scraper_tasks import ScraperTask

# 抖音企业号后台基础地址
LEADS_BASE = "https://leads.cluerich.com"
LIVE_SCREEN_URL = f"{LEADS_BASE}/pc/analysis/live-screen"
COMMENT_URL = f"{LEADS_BASE}/pc/analysis/live-comment"


class CluerichMetricsCollector(AdaptiveCollector):
    """直播指标采集器 — 从 live-screen 页面获取"""

    def __init__(self, db: Session, context: BrowserContext, task: ScraperTask, dashboard_url: str):
        super().__init__(db, context, task)
        self.dashboard_url = dashboard_url

        # 注册 API 监听模式 — 监听页面加载时的数据接口
        self.api.register_api(
            pattern="/webcast/stream/",
            handler=lambda data: {
                "online_count": data.get("data", {}).get("online_count"),
                "total_viewers": data.get("data", {}).get("total_viewers"),
            },
        )

        # DOM 兜底：提取页面中的指标数据
        self.dom.register(
            name="online_count",
            js="document.querySelector('[class*=online]')?.textContent?.trim() || '0'",
        )

    async def collect(self, url: str = "") -> dict:
        return await super().collect(url or self.dashboard_url)


class CluerichCommentCollector(AdaptiveCollector):
    """评论采集器 — 从 live-comment 页面获取"""

    def __init__(self, db: Session, context: BrowserContext, task: ScraperTask, room_id: str):
        super().__init__(db, context, task)
        self.url = f"{COMMENT_URL}?roomId={room_id}&fullscreen=0"

        # 监听评论数据接口
        self.api.register_api(
            pattern="/webcast/comment/",
            handler=lambda data: {"comments": data.get("data", [])},
        )

    async def collect(self, url: str = "") -> dict:
        return await super().collect(url or self.url)
