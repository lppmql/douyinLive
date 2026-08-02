"""直播与回放流地址采集器。"""
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

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

    @staticmethod
    def choose_stream_candidate(video_url: str | None, observed_urls: list[str]) -> str | None:
        """从页面元素和网络请求中选择最适合后续转写的真实媒体地址。

        录播页面通常会先发起 m3u8 请求，旧实现等页面加载后才注册监听，
        因而经常只拿到已经失效的直播 FLV。这里优先选择录播 m3u8，并用
        最后出现的请求打破同分候选，符合页面逐步切换清晰度的实际行为。
        """
        candidates = [*observed_urls, video_url]
        valid: list[tuple[int, int, str]] = []
        for index, value in enumerate(candidates):
            if not value:
                continue
            parsed = urlparse(value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                continue
            lowered = value.casefold()
            if ".m3u8" not in lowered and ".flv" not in lowered:
                continue
            score = 100 if ".m3u8" in lowered else 20
            if "record" in lowered or "replay" in lowered:
                score += 40
            if "third-stream" in lowered:
                score += 10
            valid.append((score, index, value))
        if not valid:
            return None
        return max(valid, key=lambda item: (item[0], item[1]))[2]

    async def fetch_stream_url(self, dashboard_url: str, session_id: int) -> Optional[str]:
        """从大屏页面提取可转写的 m3u8/FLV 地址并存储。"""
        page = await self.context.new_page()
        try:
            # 必须在 goto 前监听。录播 m3u8 往往在首屏加载阶段只请求一次，
            # 如果页面加载完成后才绑定监听，就只能退回到过期的 video.src。
            media_requests: list[str] = []

            def on_request(request):
                lowered = request.url.casefold()
                if ".m3u8" in lowered or ".flv" in lowered:
                    media_requests.append(request.url)

            page.on("request", on_request)
            await page.goto(dashboard_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)

            # video.src 作为补充候选；blob 地址会在选择器中被安全排除。
            video_url = None
            try:
                video_url = await page.evaluate("""
                    () => {
                        const v = document.querySelector('video');
                        return v ? (v.src || v.querySelector('source')?.src) : null;
                    }
                """)
            except Exception:
                pass
            stream_url = self.choose_stream_candidate(video_url, media_requests)

            if stream_url:
                # 不再 JSON.stringify，否则 ffmpeg 收到的 UA 会额外带一层引号。
                user_agent = await page.evaluate("navigator.userAgent")
                # 这里只保存候选，不能在真实拉流验证前替换当前 active。
                # 激活和旧源过期由 stream_refresh 在 probe 成功后同一事务完成。
                source = StreamSource(
                    session_id=session_id,
                    m3u8_url=stream_url[:2000],
                    headers_json={"User-Agent": user_agent, "Referer": dashboard_url},
                    status="pending",
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
