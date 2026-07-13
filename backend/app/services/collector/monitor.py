"""
开播/下播检测引擎

架构:
  ILiveStatusDetector (接口)
    ├── CluerichLiveDetector (真实实现)
    └── MockLiveDetector (Mock 实现)

  LiveStateManager — Redis 状态管理
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any

from app.core.logger import logger
from app.services.collector.browser import BrowserManager, browser_manager
from app.services.collector.collector_framework import AdaptiveCollector


@dataclass
class LiveStatusResult:
    """直播状态检测结果"""
    is_live: bool
    session_title: Optional[str] = None
    start_time: Optional[datetime] = None
    online_count: Optional[int] = None
    stream_url: Optional[str] = None
    raw_data: Optional[dict] = None


class ILiveStatusDetector(ABC):
    """直播状态检测器接口"""

    @abstractmethod
    async def detect(self, dashboard_url: str) -> LiveStatusResult:
        ...


class CluerichLiveDetector(ILiveStatusDetector):
    """Cluerich 直播状态检测器 — 使用 Playwright 访问大屏页面"""

    def __init__(self, browser_mgr: BrowserManager = None):
        self.browser_mgr = browser_mgr or browser_manager

    async def detect(self, dashboard_url: str) -> LiveStatusResult:
        """
        访问大屏页面，检测直播状态。
        API 优先监听 /webcast/ 接口，DOM 降级检测页面标识。
        """
        context = await self.browser_mgr.create_context()
        page = await context.new_page()
        try:
            captured = {"is_live": False, "data": None}

            def on_response(resp):
                url = resp.url
                if "/bff/statistic/live-screen/" in url or "/bff/statistic/live-comment/" in url:
                    content_type = resp.headers.get("content-type", "")
                    if "json" in content_type:
                        import json as _json
                        captured["data"] = resp  # lazy eval in handler

            page.on("response", on_response)
            await page.goto(dashboard_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)

            # API 结果解析
            if captured["data"]:
                try:
                    data = await captured["data"].json()
                    info = data.get("data", data.get("result", {}))
                    if isinstance(info, dict) and "data" in info:
                        info = info["data"]  # 兼容 {data: {data: ...}}
                    is_live = info.get("live_status") == 1 or info.get("is_live") is True
                    # 也通过页面文本判断
                    if not is_live:
                        pass  # 后续 DOM 降级检测
                    return LiveStatusResult(
                        is_live=is_live,
                        session_title=info.get("title") or info.get("session_title") or info.get("room_title"),
                        online_count=info.get("lp_screen_live_user_realtime") or info.get("online_count"),
                        stream_url=info.get("stream_url"),
                        raw_data=data,
                    )
                except Exception:
                    pass

            # DOM 降级：检测页面文本
            body_text = await page.evaluate("document.body?.innerText?.toLowerCase() || ''")
            has_live = any(kw in body_text for kw in ["直播中", "正在直播", "live", "online"])
            return LiveStatusResult(
                is_live=has_live,
                raw_data={"dom_text_preview": body_text[:200]},
            )
        except Exception as e:
            logger.error(f"开播检测失败: {e}")
            return LiveStatusResult(is_live=False)
        finally:
            await page.close()


class MockLiveDetector(ILiveStatusDetector):
    """
    Mock 直播状态检测器 — 预设剧本模拟状态转换

    剧本: IDLE_COUNT 次空闲 → LIVE_COUNT 次直播 → 自动回到空闲
    """

    def __init__(self, idle_count: int = 3, live_count: int = 10):
        self.idle_count = idle_count
        self.live_count = live_count
        self._check_num = 0
        self._live_num = 0
        self._is_live = False

    async def detect(self, dashboard_url: str = "") -> LiveStatusResult:
        import random
        self._check_num += 1

        if not self._is_live:
            # 空闲阶段
            if self._check_num >= self.idle_count:
                self._is_live = True
                self._live_num = 0
                self._check_num = 0
                logger.info("[Mock] 模拟开播")
                return LiveStatusResult(
                    is_live=True,
                    session_title=f"模拟直播场次_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                    start_time=datetime.utcnow(),
                    online_count=random.randint(50, 200),
                    stream_url="https://mock.stream/live.m3u8",
                )
            return LiveStatusResult(is_live=False)

        # 直播阶段
        self._live_num += 1
        if self._live_num >= self.live_count:
            self._is_live = False
            self._check_num = 0
            logger.info("[Mock] 模拟下播")
            return LiveStatusResult(is_live=False)

        return LiveStatusResult(
            is_live=True,
            online_count=random.randint(50, 300),
        )
