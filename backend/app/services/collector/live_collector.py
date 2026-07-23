"""
直播采集器 — 指标/评论/画像

每个采集器继承 AdaptiveCollector，复用 API 优先 + DOM 降级框架。
"""
from datetime import datetime
from sqlalchemy.orm import Session
from playwright.async_api import BrowserContext

from app.models.scraper_tasks import ScraperTask
from app.services.collector.collector_framework import AdaptiveCollector
from app.services.collector.comments import _parse_comment_user_profile


class MetricsCollector(AdaptiveCollector):
    """直播指标采集器 — 在线人数、曝光、点赞等"""

    def __init__(self, db: Session, context: BrowserContext, task: ScraperTask, dashboard_url: str):
        super().__init__(db, context, task)
        self.dashboard_url = dashboard_url

        self.api.register_api(
            pattern="/bff/statistic/live-screen/",
            handler=lambda data: self._parse_metrics(data),
        )
        self.dom.register(
            name="online_count",
            # 没有匹配到页面可见数值时返回 None，避免把无权限页面写成全零趋势。
            js="document.querySelector('[class*=online]')?.textContent?.trim() || null",
        )

    def _parse_metrics(self, data: dict) -> dict:
        # Cluerich BFF API 返回结构: {"data": {...}, "error_code": 0}
        info = data.get("data", data.get("result", {}))
        if isinstance(info, dict) and "data" in info:
            info = info["data"]  # 兼容 {data: {data: {...}}}

        def _first(keys):
            for k in keys:
                v = info.get(k)
                if v is not None:
                    return v
            return None

        return {
            "online_count": _first(["lp_screen_live_user_realtime", "online_count"]),
            "exposure_count": _first(["lp_screen_live_enter_users", "exposure_count"]),
            "enter_count": _first(["lp_screen_live_enter_users", "enter_count"]),
            "like_count": _first(["lp_screen_live_like_count", "like_count"]),
            "comment_count": _first(["lp_screen_live_comment_count", "comment_count"]),
            "follow_count": _first(["lp_screen_live_new_follow_count", "follow_count"]),
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
            pattern="/bff/statistic/live-comment/",
            handler=lambda data: self._parse_comments(data),
        )

    def _parse_comments(self, data: dict) -> dict:
        # Cluerich 评论 API: {"data": {"list": [...]}}
        info = data.get("data", data.get("result", {}))
        if isinstance(info, dict):
            comments_raw = info.get("list") or info.get("comments") or info.get("data", [])
        else:
            comments_raw = info if isinstance(info, list) else []
        parsed = []
        for c in comments_raw:
            if not isinstance(c, dict):
                continue
            profile = _parse_comment_user_profile(c)
            parsed.append({
                **profile,
                "user_sec_uid": c.get("user_sec_uid") or c.get("secUId") or c.get("sec_uid"),
                "webcast_uid": c.get("webcast_uid") or c.get("webcastUid"),
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
            pattern="/bff/statistic/live-screen/audience",
            handler=lambda data: self._parse_profiles(data),
        )

    def _parse_profiles(self, data: dict) -> dict:
        # Cluerich 画像 API: {"data": {"age": [...], "gender": [...]}}
        info = data.get("data", {})
        if isinstance(info, dict) and "data" in info:
            info = info["data"]  # 兼容嵌套
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
