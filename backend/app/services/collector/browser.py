"""
浏览器管理器 — 单例模式管理 Playwright Chromium 实例

职责:
1. 全局 Chromium 浏览器实例生命周期管理（惰性初始化）
2. 基于 StorageState 创建/恢复浏览器上下文
3. 执行扫码登录流程（有头模式）
4. 持久化/恢复 StorageState
5. 检测登录态是否过期
"""
import asyncio
import base64
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext

from app.core.logger import logger

# 浏览器状态存储目录
STORAGE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "storage_state"
STORAGE_DIR.mkdir(exist_ok=True)

# 抖音企业号后台地址
LEADS_BASE = "https://leads.cluerich.com"
LOGIN_URL = f"{LEADS_BASE}/pc/auth/login"
HOME_URL = f"{LEADS_BASE}/pc/growth/home"


class BrowserManager:
    """浏览器管理器单例"""

    _instance: Optional["BrowserManager"] = None
    _playwright = None
    _browser: Optional[Browser] = None
    _initialized: bool = False
    # 登录会话状态（内存共享）
    login_sessions: dict[int, dict] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    async def ensure_browser(self, headless: bool = True) -> Browser:
        """获取或创建浏览器实例"""
        if self._browser is None or not self._browser.is_connected():
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=headless,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            logger.info("浏览器实例已创建")
        return self._browser

    async def create_context(self, storage_state_path: Optional[str] = None) -> BrowserContext:
        """创建浏览器上下文，可恢复之前的登录状态"""
        browser = await self.ensure_browser()
        opts = {}
        if storage_state_path and Path(storage_state_path).exists():
            opts["storage_state"] = storage_state_path
        return await browser.new_context(**opts)

    async def save_storage_state(self, context: BrowserContext, account_id: int) -> str:
        """保存 StorageState 到文件，返回文件路径"""
        path = str(STORAGE_DIR / f"account_{account_id}.json")
        await context.storage_state(path=path)
        logger.info(f"StorageState 已保存: {path}")
        return path

    async def start_qr_login(self, task_id: int, account_name: str = "默认账号") -> dict:
        """
        启动扫码登录（后台有头浏览器）

        返回: {"qr_base64": str, "message": str}
        """
        self.login_sessions[task_id] = {
            "status": "pending",
            "qr_base64": "",
            "account_id": None,
            "message": "正在启动浏览器...",
        }

        asyncio.create_task(self._qr_login_worker(task_id, account_name))

        return {"qr_base64": "", "message": "登录任务已创建"}

    async def _qr_login_worker(self, task_id: int, account_name: str):
        """后台扫码登录工作线程"""
        playwright = None
        browser = None
        try:
            self.login_sessions[task_id]["status"] = "scanning"
            self.login_sessions[task_id]["message"] = "正在打开浏览器..."

            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                ],
            )

            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
            )
            page = await context.new_page()

            # 1. 导航到登录页面
            await page.goto(LOGIN_URL, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            logger.info(f"登录页已加载: {page.url}")

            # 2. 点击抖音图标，弹出二维码
            try:
                douyin_icon = await page.wait_for_selector(
                    "//span[@class='icon douyin']//img",
                    timeout=10000,
                )
                await douyin_icon.click()
                self.login_sessions[task_id]["message"] = "已选择抖音登录..."
                await asyncio.sleep(3)
                logger.info("已点击抖音图标")
            except Exception as e:
                logger.warning(f"未找到抖音图标: {e}")

            # 3. 等待二维码出现并截图
            await asyncio.sleep(2)
            try:
                await page.wait_for_selector(
                    "canvas, img[src*='qr'], img[src*='qrcode'], [class*='qrcode']",
                    timeout=15000,
                )
            except Exception:
                pass

            try:
                screenshot = await page.screenshot(full_page=False)
                self.login_sessions[task_id]["qr_base64"] = base64.b64encode(screenshot).decode()
                self.login_sessions[task_id]["page_url"] = page.url
                self.login_sessions[task_id]["message"] = "请使用抖音扫码登录"
                logger.info(f"二维码截图完成: {len(screenshot)} 字节")
            except Exception as e:
                self.login_sessions[task_id]["message"] = f"截图失败: {str(e)[:50]}"

            # 4. 等待登录成功（最长 120 秒）
            try:
                await page.wait_for_url(
                    lambda url: LEADS_BASE in url and "/auth/" not in url,
                    timeout=120000,
                )
                self.login_sessions[task_id]["status"] = "success"
                self.login_sessions[task_id]["message"] = "登录成功"

                # 保存 StorageState（Cookie 等）
                storage_path = await self._save_context_state(context, task_id)

                ua = await page.evaluate("navigator.userAgent")
                vp = page.viewport_size

                self.login_sessions[task_id].update({
                    "storage_path": storage_path,
                    "user_agent": ua,
                    "viewport_width": vp.get("width") if vp else None,
                    "viewport_height": vp.get("height") if vp else None,
                })
                logger.info(f"扫码登录成功! storage_path={storage_path}")
            except Exception as e:
                self.login_sessions[task_id]["status"] = "timeout"
                self.login_sessions[task_id]["message"] = "登录超时，请重新扫码"

        except Exception as e:
            logger.error(f"扫码登录失败: {e}")
            self.login_sessions[task_id]["status"] = "failed"
            self.login_sessions[task_id]["message"] = f"登录失败: {str(e)}"
        finally:
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()

    async def _save_context_state(self, context: BrowserContext, task_id: int) -> str:
        """保存上下文状态到文件"""
        path = str(STORAGE_DIR / f"login_task_{task_id}.json")
        await context.storage_state(path=path)
        return path

    async def get_login_qr(self, task_id: int) -> Optional[str]:
        """获取登录会话的二维码 base64"""
        session = self.login_sessions.get(task_id)
        if session:
            return session.get("qr_base64", "")
        return None

    async def get_login_status(self, task_id: int) -> dict:
        """获取登录会话状态"""
        session = self.login_sessions.get(task_id)
        if not session:
            return {"status": "not_found", "message": "登录任务不存在"}
        return {
            "status": session.get("status", "pending"),
            "qr_base64": session.get("qr_base64", ""),
            "account_id": session.get("account_id"),
            "storage_path": session.get("storage_path"),
            "user_agent": session.get("user_agent"),
            "viewport_width": session.get("viewport_width"),
            "viewport_height": session.get("viewport_height"),
            "message": session.get("message", ""),
        }

    async def check_login_expired(self, context: BrowserContext) -> bool:
        """检查登录是否过期"""
        page = await context.new_page()
        try:
            await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=15000)
            expired = "login" in page.url.lower() or "/auth/" in page.url
            return expired
        except Exception:
            return True
        finally:
            await page.close()

    async def close(self):
        """关闭浏览器"""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.info("浏览器实例已关闭")


# 全局单例
browser_manager = BrowserManager()
