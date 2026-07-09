"""
直播采集器 — 指标/评论/画像

每个采集器继承 AdaptiveCollector，复用 API 优先 + DOM 降级框架。
"""
from datetime import datetime
from sqlalchemy.orm import Session
from playwright.async_api import BrowserContext

from app.models.scraper_tasks import ScraperTask
from app.services.collector.collector_framework import AdaptiveCollector


class MetricsCollector(AdaptiveCollector):
    """直播指标采集器 — 在线人数、曝光、点赞等"""

    def __init__(self, db: Session, context: BrowserContext, task: ScraperTask, dashboard_url: str):
        super().__init__(db, context, task)
        self.dashboard_url = dashboard_url

        self.api.register_api(
            pattern="/webcast/stream/",
            handler=lambda data: self._parse_metrics(data),
        )
        self.dom.register(
            name="online_count",
            js="document.querySelector('[class*=online]')?.textContent?.trim() || '0'",
        )

    def _parse_metrics(self, data: dict) -> dict:
        info = data.get("data", data.get("result", {}))
        return {
            "online_count": info.get("online_count"),
            "exposure_count": info.get("exposure_count"),
            "enter_count": info.get("enter_count"),
            "like_count": info.get("like_count"),
            "comment_count": info.get("comment_count"),
            "follow_count": info.get("follow_count"),
        }

    async def collect(self, url: str = "") -> dict:
        return await super().collect(url or self.dashboard_url)


class CommentCollector(AdaptiveCollector):
    """评论采集器"""

    def __init__(self, db: Session, context: BrowserContext, task: ScraperTask, dashboard_url: str):
        super().__init__(db, context, task)
        self.dashboard_url = dashboard_url
        self._last_time: datetime | None = None

        self.api.register_api(
            pattern="/webcast/comment/",
            handler=lambda data: self._parse_comments(data),
        )

    def _parse_comments(self, data: dict) -> dict:
        comments_raw = data.get("data", data.get("result", []))
        if isinstance(comments_raw, dict):
            comments_raw = comments_raw.get("list", [])
        parsed = []
        for c in comments_raw:
            parsed.append({
                "user_nickname": c.get("user_nickname", c.get("nickname")),
                "comment_content": c.get("comment_content", c.get("content")),
                "comment_time": c.get("comment_time") or datetime.utcnow(),
            })
        return {"comments": parsed}

    async def collect(self, url: str = "") -> dict:
        return await super().collect(url or self.dashboard_url)


class ProfileCollector(AdaptiveCollector):
    """用户画像采集器 — 年龄/性别/地域"""

    def __init__(self, db: Session, context: BrowserContext, task: ScraperTask, dashboard_url: str):
        super().__init__(db, context, task)
        self.dashboard_url = dashboard_url

        self.api.register_api(
            pattern="/webcast/audience/",
            handler=lambda data: self._parse_profiles(data),
        )

    def _parse_profiles(self, data: dict) -> dict:
        info = data.get("data", {})
        profiles = []
        for dim in ("age", "gender", "region", "province", "city"):
            items = info.get(dim, [])
            for item in items:
                profiles.append({
                    "dimension_type": dim,
                    "dimension_name": item.get("name"),
                    "ratio": item.get("ratio", 0),
                    "count": item.get("count", 0),
                })
        return {"profiles": profiles}

    async def collect(self, url: str = "") -> dict:
        return await super().collect(url or self.dashboard_url)
