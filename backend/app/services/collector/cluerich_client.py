"""
Cluerich 直播后台采集客户端

封装 Cluerich 平台的特定采集逻辑，基于自适应采集框架。
Phase 3 只搭建基础骨架，Phase 4 完善具体采集。
"""
from sqlalchemy.orm import Session
from playwright.async_api import BrowserContext

from app.services.collector.collector_framework import AdaptiveCollector
from app.models.scraper_tasks import ScraperTask


class CluerichMetricsCollector(AdaptiveCollector):
    """直播指标采集器 (Phase 4 完善)"""

    def __init__(self, db: Session, context: BrowserContext, task: ScraperTask, dashboard_url: str):
        super().__init__(db, context, task)
        self.dashboard_url = dashboard_url

        # 注册 API 监听模式（子串匹配，不硬编码完整路径）
        self.api.register_api(
            pattern="/webcast/stream/",
            handler=lambda data: {
                "online_count": data.get("data", {}).get("online_count"),
                "total_viewers": data.get("data", {}).get("total_viewers"),
            },
        )

        # 注册 DOM 兜底规则
        self.dom.register(
            name="online_count",
            js="document.querySelector('[class*=online]')?.textContent?.trim() || '0'",
        )

    async def collect(self, url: str = "") -> dict:
        return await super().collect(url or self.dashboard_url)


class CluerichCommentCollector(AdaptiveCollector):
    """评论采集器 (Phase 4 完善)"""

    def __init__(self, db: Session, context: BrowserContext, task: ScraperTask):
        super().__init__(db, context, task)

        self.api.register_api(
            pattern="/webcast/comment/",
            handler=lambda data: {"comments": data.get("data", [])},
        )
