"""m3u8 流地址采集器"""
from datetime import datetime
from typing import Optional

from playwright.async_api import BrowserContext
from sqlalchemy.orm import Session

from app.core.logger import logger
from app.models.stream_sources import StreamSource
from app.models.scraper_logs import ScraperLog


class StreamCollector:
    """m3u8 流地址采集器 — 从大屏页面提取直播流 URL"""

    def __init__(self, db: Session, context: BrowserContext):
        self.db = db
        self.context = context

    async def fetch_stream_url(self, dashboard_url: str, session_id: int) -> Optional[str]:
        """从大屏页面提取 m3u8 地址并存储"""
        page = await self.context.new_page()
        try:
            await page.goto(dashboard_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)

            # 尝试从页面提取流地址
            stream_url = None

            # 1. 从 video 元素提取
            try:
                stream_url = await page.evaluate("""
                    () => {
                        const v = document.querySelector('video');
                        return v ? (v.src || v.querySelector('source')?.src) : null;
                    }
                """)
            except Exception:
                pass

            # 2. 从网络请求中捕获 m3u8
            if not stream_url:
                m3u8_requests = []
                def on_request(req):
                    if '.m3u8' in req.url:
                        m3u8_requests.append(req.url)
                page.on("request", on_request)
                await page.wait_for_timeout(3000)
                if m3u8_requests:
                    stream_url = m3u8_requests[-1]

            if stream_url:
                headers = await page.evaluate("JSON.stringify(navigator.userAgent)")
                source = StreamSource(
                    session_id=session_id,
                    m3u8_url=stream_url[:2000],
                    headers_json={"User-Agent": headers},
                    status="active",
                    fetched_at=datetime.utcnow(),
                )
                self.db.add(source)
                self.db.commit()
                logger.info(f"流地址已采集: session={session_id} url={stream_url[:80]}...")
                return stream_url

            logger.warning(f"未找到流地址: session={session_id}")
            return None

        except Exception as e:
            log = ScraperLog(level="error", message=f"流地址采集失败: {e}")
            self.db.add(log)
            self.db.commit()
            return None
        finally:
            try:
                await page.close()
            except Exception as exc:
                text = str(exc).lower()
                if "handler is closed" not in text and "target page, context or browser has been closed" not in text:
                    logger.debug("流地址页面关闭失败: %s", exc)
