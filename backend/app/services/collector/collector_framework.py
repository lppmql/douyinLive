"""
采集器框架 — API 优先、DOM 降级

架构:
  BaseCollector (抽象基类)
    ├── ApiCollector (API 监听优先)
    ├── DomFallbackCollector (DOM 解析降级)
    └── AdaptiveCollector (组合: API → DOM 自适应)
"""
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Optional, Callable

from playwright.async_api import BrowserContext, Page, Response
from sqlalchemy.orm import Session

from app.core.logger import logger
from app.models.scraper_tasks import ScraperTask
from app.models.scraper_logs import ScraperLog


class BaseCollector(ABC):
    """采集器抽象基类"""

    def __init__(self, db: Session, context: BrowserContext, task: ScraperTask):
        self.db = db
        self.context = context
        self.task = task
        self.page: Optional[Page] = None

    def log(self, level: str, message: str, raw_json: Any = None):
        """记录采集日志到 scraper_logs 表"""
        log_entry = ScraperLog(
            task_id=self.task.id,
            level=level,
            message=message,
            raw_json=raw_json,
        )
        self.db.add(log_entry)
        self.db.commit()
        logger.info(f"[Collector] {level.upper()}: {message}")

    async def ensure_page(self, url: str):
        """打开页面（复用或新建）"""
        if self.page is None:
            self.page = await self.context.new_page()
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            self.log("warn", f"页面加载超时: {url[:60]}... - {e}")

    async def close(self):
        """清理资源"""
        if self.page:
            await self.page.close()
            self.page = None

    @abstractmethod
    async def collect(self, url: str) -> dict:
        """执行采集，返回数据字典"""


class ApiCollector(BaseCollector):
    """
    API 优先采集器

    监听页面 response 事件 → 匹配 URL 模式 → 提取 JSON 数据
    """

    def __init__(self, db: Session, context: BrowserContext, task: ScraperTask):
        super().__init__(db, context, task)
        self._patterns: list[tuple[str, Callable]] = []
        self._captured: list[dict] = []

    def register_api(self, pattern: str, handler: Callable):
        """
        注册 API 监听模式

        pattern: URL 子串匹配
        handler: (json_data) -> dict  提取函数
        """
        self._patterns.append((pattern, handler))

    async def _on_response(self, response: Response):
        """response 事件回调"""
        url = response.url
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type:
            return

        for pattern, handler in self._patterns:
            if pattern in url:
                try:
                    data = await response.json()
                    self._captured.append({"url": url, "data": data})
                    self.log("info", f"API 匹配: {pattern}", raw_json=data)
                except Exception as e:
                    self.log("warn", f"API 解析失败: {pattern} - {e}")

    async def collect(self, url: str) -> dict:
        """执行 API 采集"""
        self._captured.clear()
        await self.ensure_page(url)

        self.page.on("response", self._on_response)

        try:
            await self.page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass

        await asyncio.sleep(2)

        result = {}
        for pattern, handler in self._patterns:
            matched = [c for c in self._captured if pattern in c["url"]]
            if matched:
                try:
                    extracted = handler(matched[-1]["data"])
                    result.update(extracted)
                except Exception as e:
                    self.log("warn", f"数据提取失败 ({pattern}): {e}")

        return result


class DomFallbackCollector(BaseCollector):
    """
    DOM 兜底采集器

    当 API 采集失败时，用 JS 表达式从 DOM 提取数据
    """

    def __init__(self, db: Session, context: BrowserContext, task: ScraperTask):
        super().__init__(db, context, task)
        self._extractors: list[dict] = []

    def register(self, name: str, js: str, default: Any = None):
        """注册 DOM 提取规则"""
        self._extractors.append({"name": name, "js": js, "default": default})

    async def collect(self, url: str) -> dict:
        """执行 DOM 采集"""
        await self.ensure_page(url)
        try:
            await self.page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass

        result = {}
        for ext in self._extractors:
            try:
                value = await self.page.evaluate(ext["js"])
                result[ext["name"]] = value if value is not None else ext["default"]
            except Exception as e:
                result[ext["name"]] = ext["default"]
                self.log("warn", f"DOM 提取失败 ({ext['name']}): {e}")

        return result


class AdaptiveCollector:
    """
    自适应采集器 — API 优先、DOM 降级

    先尝试 ApiCollector，数据为空则降级 DomFallbackCollector
    """

    def __init__(self, db: Session, context: BrowserContext, task: ScraperTask):
        self.api = ApiCollector(db, context, task)
        self.dom = DomFallbackCollector(db, context, task)

    async def collect(self, url: str) -> dict:
        """自适应采集"""
        self.api.log("info", f"开始采集: {url[:80]}")

        result = await self.api.collect(url)
        if result:
            self.api.log("info", f"API 采集成功: {len(result)} 个字段")
            return result

        self.api.log("warn", "API 无数据，降级 DOM 解析")
        result = await self.dom.collect(url)

        if result:
            self.api.log("info", f"DOM 采集成功: {len(result)} 个字段")
        else:
            self.api.log("error", "API 和 DOM 均采集失败")

        return result

    async def close(self):
        await self.api.close()
        await self.dom.close()
