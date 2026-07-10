"""
浏览器管理器 — 单例模式管理 Playwright Chromium 实例

核心设计：
1. 登录上下文持久化 — 登录成功后保持浏览器上下文不关闭，后续采集复用同一会话
2. 指纹一致性 — 固定 User-Agent、Viewport、浏览器参数，不被平台检测为不同设备
3. Cookie 自动刷新 — 每次采集后保存最新 StorageState，下次可恢复
4. 登录态检测 — 每次采集前验证 Cookie 是否仍然有效
"""
import asyncio
import base64
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from app.core.logger import logger
from app.core.database import SessionLocal
from app.models.scraper_accounts import ScraperAccount
from app.models.scraper_tasks import ScraperTask

# 浏览器状态存储目录
STORAGE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "storage_state"
STORAGE_DIR.mkdir(exist_ok=True)

# 抖音企业号后台地址
LEADS_BASE = "https://leads.cluerich.com"
LOGIN_URL = f"{LEADS_BASE}/pc/auth/login"

# 统一指纹参数（登录 + 采集用同一套）
DEFAULT_FINGERPRINT = {
    "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "viewport": {"width": 1920, "height": 1080},
    "locale": "zh-CN",
    "timezone_id": "Asia/Shanghai",
    "device_scale_factor": 1,
    "color_scheme": "light",
}

# 浏览器启动参数
BROWSER_ARGS = [
    "--headless=new",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-blink-features=AutomationControlled",
    "--disable-web-security",
    "--disable-features=IsolateOrigins,site-per-process",
]

# 初始化脚本：覆盖指纹检测
FINGERPRINT_SCRIPT = """
// 覆盖 webdriver 检测
Object.defineProperty(navigator, 'webdriver', { get: () => false });
// 覆盖 chrome 检测
window.chrome = { runtime: {} };
// 覆盖权限查询
const originalQuery = navigator.permissions.query;
navigator.permissions.query = (p) => (
    p.name === 'notifications' ? Promise.resolve({ state: 'denied' }) : originalQuery(p)
);
// 覆盖 plugins
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});
// 覆盖 languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['zh-CN', 'zh', 'en'],
});
"""


class BrowserManager:
    """浏览器管理器单例"""

    _instance: Optional["BrowserManager"] = None
    _playwright = None
    _browser: Optional[Browser] = None
    _initialized: bool = False
    # 持久化登录上下文（登录成功后保持不关闭）
    _logged_in_context: Optional[BrowserContext] = None
    _logged_in_account_id: Optional[int] = None
    _logged_in_storage_path: Optional[str] = None
    # 登录会话状态（内存共享）
    login_sessions: dict[int, dict] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    async def ensure_browser(self) -> Browser:
        """获取或创建浏览器实例（固定参数）"""
        if self._browser is None or not self._browser.is_connected():
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=BROWSER_ARGS,
            )
            logger.info("浏览器实例已创建")
        return self._browser

    def _make_context_opts(
        self,
        storage_state_path: Optional[str] = None,
        fingerprint: Optional[dict[str, Any]] = None
    ) -> dict:
        """生成浏览器上下文参数，优先复用账号自身指纹。"""
        fingerprint = fingerprint or {}
        viewport = fingerprint.get("viewport") or DEFAULT_FINGERPRINT["viewport"]
        opts = {
            "user_agent": fingerprint.get("user_agent") or DEFAULT_FINGERPRINT["user_agent"],
            "viewport": {
                "width": int(viewport.get("width", DEFAULT_FINGERPRINT["viewport"]["width"])),
                "height": int(viewport.get("height", DEFAULT_FINGERPRINT["viewport"]["height"])),
            },
            "locale": fingerprint.get("locale") or DEFAULT_FINGERPRINT["locale"],
            "timezone_id": fingerprint.get("timezone_id") or DEFAULT_FINGERPRINT["timezone_id"],
            "device_scale_factor": fingerprint.get("device_scale_factor") or DEFAULT_FINGERPRINT["device_scale_factor"],
            "color_scheme": fingerprint.get("color_scheme") or DEFAULT_FINGERPRINT["color_scheme"],
        }
        if storage_state_path and Path(storage_state_path).exists():
            opts["storage_state"] = storage_state_path
        return opts

    def _load_account_fingerprint(self, account: Optional[ScraperAccount]) -> dict[str, Any]:
        """从账号记录中解析浏览器指纹。"""
        if not account:
            return {}

        raw = account.browser_fingerprint_json
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                logger.warning("browser_fingerprint_json 解析失败，回退到基础指纹字段")

        if account.user_agent or account.viewport_width or account.viewport_height:
            return {
                "user_agent": account.user_agent,
                "viewport": {
                    "width": account.viewport_width or DEFAULT_FINGERPRINT["viewport"]["width"],
                    "height": account.viewport_height or DEFAULT_FINGERPRINT["viewport"]["height"],
                },
                "locale": DEFAULT_FINGERPRINT["locale"],
                "timezone_id": DEFAULT_FINGERPRINT["timezone_id"],
                "device_scale_factor": DEFAULT_FINGERPRINT["device_scale_factor"],
                "color_scheme": DEFAULT_FINGERPRINT["color_scheme"],
            }
        return {}

    def _find_account_by_storage_path(self, storage_state_path: Optional[str]) -> Optional[ScraperAccount]:
        """通过 storage_state_path 查找账号。"""
        if not storage_state_path:
            return None

        db = SessionLocal()
        try:
            return db.query(ScraperAccount).filter(
                ScraperAccount.storage_state_path == storage_state_path
            ).order_by(ScraperAccount.id.desc()).first()
        finally:
            db.close()

    def _find_account_by_id(self, account_id: Optional[int]) -> Optional[ScraperAccount]:
        """通过账号 ID 查找账号。"""
        if not account_id:
            return None

        db = SessionLocal()
        try:
            return db.query(ScraperAccount).get(account_id)
        finally:
            db.close()

    async def create_context(
        self,
        storage_state_path: Optional[str] = None,
        fingerprint: Optional[dict[str, Any]] = None
    ) -> BrowserContext:
        """创建浏览器上下文，可恢复之前的登录状态。"""
        browser = await self.ensure_browser()
        opts = self._make_context_opts(storage_state_path, fingerprint)
        context = await browser.new_context(**opts)
        # 注入反检测脚本
        await context.add_init_script(FINGERPRINT_SCRIPT)
        return context

    async def get_logged_in_context(self) -> tuple[Optional[BrowserContext], bool, str]:
        """
        获取已登录的浏览器上下文（优先使用保持中的登录上下文）

        返回: (context, is_valid, message)
        """
        # 如果有保持中的登录上下文，检查是否仍然有效
        if self._logged_in_context:
            try:
                # 尝试打开新页面来验证上下文是否可用
                test_page = await self._logged_in_context.new_page()
                await test_page.close()
                is_valid = not await self.check_login_expired(self._logged_in_context)
                if is_valid:
                    logger.info("复用持久化登录上下文")
                    return self._logged_in_context, True, "ok"
                else:
                    logger.warning("持久化上下文 Cookie 已过期")
                    return self._logged_in_context, False, "登录已过期，请重新扫码"
            except Exception as e:
                logger.warning(f"持久化上下文不可用: {e}")
                self._logged_in_context = None

        # 没有持久化上下文，从 StorageState 文件恢复
        if not self._logged_in_storage_path:
            return None, False, "没有登录账号"

        account = self._find_account_by_id(self._logged_in_account_id)
        if account is None:
            account = self._find_account_by_storage_path(self._logged_in_storage_path)
        fingerprint = self._load_account_fingerprint(account)

        context = await self.create_context(self._logged_in_storage_path, fingerprint)
        if not context:
            return None, False, "浏览器启动失败"

        is_valid = not await self.check_login_expired(context)
        if is_valid:
            # 保存为持久化上下文
            self._logged_in_context = context
            logger.info("从 StorageState 恢复登录上下文并保持")
            return context, True, "ok"

        await context.close()
        return None, False, "登录已过期，请重新扫码登录"

    async def set_logged_in_context(self, context: BrowserContext, storage_path: str, account_id: int):
        """
        设置持久化登录上下文（登录成功后调用）

        替换旧的持久化上下文（如果存在则关闭旧的）
        """
        if self._logged_in_context and self._logged_in_context != context:
            try:
                await self._logged_in_context.close()
            except Exception:
                pass

        self._logged_in_context = context
        self._logged_in_storage_path = storage_path
        self._logged_in_account_id = account_id
        logger.info(f"持久化登录上下文已设置: account_id={account_id}")

    async def refresh_logged_in_state(self):
        """
        刷新持久化登录上下文的 StorageState
        每次采集成功后调用，延长 Cookie 有效期
        """
        if self._logged_in_context and self._logged_in_storage_path:
            try:
                await self._logged_in_context.storage_state(path=self._logged_in_storage_path)
                state = await self._logged_in_context.storage_state()
                cookies_json = json.dumps(state.get("cookies", []), ensure_ascii=False)
                self._update_account_state(
                    account_id=self._logged_in_account_id,
                    storage_path=self._logged_in_storage_path,
                    cookies_json=cookies_json,
                )
                logger.info(f"持久化上下文 Cookie 已刷新: {self._logged_in_storage_path}")
            except Exception as e:
                logger.warning(f"刷新 Cookie 失败: {e}")

    async def start_qr_login(
        self,
        task_id: int,
        account_name: str = "默认账号",
        account_id: Optional[int] = None
    ) -> dict:
        """
        启动扫码登录（后台无头浏览器）

        返回: {"qr_base64": str, "message": str}
        """
        self.login_sessions[task_id] = {
            "status": "pending",
            "qr_base64": "",
            "account_id": None,
            "target_account_id": account_id,
            "account_name": account_name,
            "message": "正在启动浏览器...",
        }

        asyncio.create_task(self._qr_login_worker(task_id, account_name, account_id))

        return {"qr_base64": "", "message": "登录任务已创建"}

    async def _qr_login_worker(self, task_id: int, account_name: str, account_id: Optional[int] = None):
        """后台扫码登录工作线程"""
        playwright = None
        browser = None
        try:
            self.login_sessions[task_id]["status"] = "scanning"
            self.login_sessions[task_id]["message"] = "正在打开浏览器..."

            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(
                headless=True,
                args=BROWSER_ARGS,
            )

            existing_account = self._find_account_by_id(account_id)
            fingerprint = self._load_account_fingerprint(existing_account)

            context = await browser.new_context(**self._make_context_opts(fingerprint=fingerprint))
            await context.add_init_script(FINGERPRINT_SCRIPT)

            page = await context.new_page()

            # 1. 导航到登录页面
            await page.goto(LOGIN_URL, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            logger.info(f"登录页已加载: {page.url}")

            # 2. 查找抖音登录按钮
            douyin_btn = None
            selectors = [
                "//span[@class='icon douyin']//img",
                "//span[contains(@class, 'douyin')]",
                "img[src*='aweme']",
                "//img[contains(@src, 'aweme')]",
            ]
            for sel in selectors:
                try:
                    douyin_btn = await page.wait_for_selector(sel, timeout=5000)
                    if douyin_btn:
                        logger.info(f"找到抖音登录按钮: {sel}")
                        break
                except Exception:
                    continue

            if not douyin_btn:
                logger.error("未找到抖音登录按钮")
                self.login_sessions[task_id]["message"] = "未找到抖音登录入口"
                self.login_sessions[task_id]["status"] = "failed"
                return

            # 3. 准备监听弹窗
            popup_future = asyncio.get_event_loop().create_future()

            async def on_popup(popup):
                logger.info(f"检测到弹窗: {popup.url[:100]}")
                if not popup_future.done():
                    popup_future.set_result(popup)

            page.on("popup", lambda p: asyncio.ensure_future(on_popup(p)))

            # 4. 点击抖音登录按钮
            await douyin_btn.click()
            self.login_sessions[task_id]["message"] = "已选择抖音登录..."
            await asyncio.sleep(3)
            logger.info("已点击抖音图标")

            # 5. 获取 QR 码
            qr_page = page
            try:
                popup = await asyncio.wait_for(
                    asyncio.shield(popup_future), timeout=5
                )
                qr_page = popup
                logger.info(f"OAuth 在弹窗中打开: {popup.url[:100]}")
                await asyncio.sleep(3)
            except asyncio.TimeoutError:
                logger.info("无弹窗，QR 码在主页面中")

            qr_base64 = ""
            try:
                imgs = await qr_page.query_selector_all("img[src*='data:image/png;base64']")
                candidates = []
                for img in imgs:
                    src = (await img.get_attribute("src")) or ""
                    if src.startswith("data:image/png;base64"):
                        candidates.append(src)
                if candidates:
                    qr_base64 = max(candidates, key=len)
                    if "," in qr_base64:
                        qr_base64 = qr_base64.split(",", 1)[1]
                    logger.info(f"二维码已提取: {len(qr_base64)} 字节")
            except Exception as e:
                logger.warning(f"提取二维码失败: {e}")

            if qr_base64:
                self.login_sessions[task_id]["qr_base64"] = qr_base64
                self.login_sessions[task_id]["page_url"] = page.url
                self.login_sessions[task_id]["message"] = "请使用抖音扫码登录"

            # 6. 等待登录成功（最长 120 秒）
            try:
                await page.wait_for_url(
                    lambda url: LEADS_BASE in url and "/auth/" not in url,
                    timeout=120000,
                )
                await asyncio.sleep(3)  # 等待页面完全加载

                self.login_sessions[task_id]["status"] = "success"
                self.login_sessions[task_id]["message"] = "登录成功"
                self.login_sessions[task_id]["final_url"] = page.url

                # 保存 StorageState
                storage_path, cookies_json = await self._save_context_state(context, task_id)
                fingerprint_snapshot = await self._capture_fingerprint(page)
                ua = fingerprint_snapshot.get("user_agent")
                vp = fingerprint_snapshot.get("viewport") or {}

                self.login_sessions[task_id].update({
                    "storage_path": storage_path,
                    "cookies_json": cookies_json,
                    "browser_fingerprint_json": json.dumps(fingerprint_snapshot, ensure_ascii=False),
                    "user_agent": ua,
                    "viewport_width": vp.get("width") if vp else None,
                    "viewport_height": vp.get("height") if vp else None,
                })

                # 直接写入数据库（不依赖前端轮询）
                saved_account_id = self._save_account_to_db(
                    task_id=task_id,
                    account_id=account_id,
                    account_name=account_name,
                    storage_path=storage_path,
                    cookies_json=cookies_json,
                    browser_fingerprint_json=json.dumps(fingerprint_snapshot, ensure_ascii=False),
                    ua=ua,
                    vp_width=vp.get("width") if vp else None,
                    vp_height=vp.get("height") if vp else None,
                )
                self.login_sessions[task_id]["account_id"] = saved_account_id

                # 将登录上下文设置为持久化上下文（不关闭浏览器！）
                await self.set_logged_in_context(context, storage_path, saved_account_id or task_id)
                logger.info(
                    f"扫码登录完成! storage_path={storage_path}, "
                    f"final_url={page.url}, account_id={saved_account_id}, 上下文已持久化"
                )

                # 验证登录是否真正成功
                await asyncio.sleep(2)
                live_check = await context.new_page()
                try:
                    await live_check.goto(
                        f"{LEADS_BASE}/pc/analysis/live-screen?room_id=check",
                        wait_until="domcontentloaded", timeout=10000
                    )
                    await asyncio.sleep(2)
                    check_url = live_check.url
                    check_body = await live_check.evaluate("document.body?.innerText || ''")
                    if "手机登录" in check_body or "login" in check_url.lower():
                        logger.warning(f"登录验证未通过，页面仍为登录页: {check_url}")
                        self.login_sessions[task_id]["message"] = "登录可能未完成，请重试"
                    else:
                        logger.info("登录验证通过，可正常访问大屏页")
                        self.login_sessions[task_id]["message"] = "登录成功，Cookie 已验证"
                except Exception as ve:
                    logger.warning(f"登录验证异常: {ve}")
                finally:
                    await live_check.close()

            except Exception as e:
                self.login_sessions[task_id]["status"] = "timeout"
                self.login_sessions[task_id]["message"] = "登录超时，请重新扫码"
                logger.warning(f"扫码登录超时: {e}")
                # 即使超时也保存上下文（可能部分登录成功）
                try:
                    await self.set_logged_in_context(context,
                        str(STORAGE_DIR / f"login_task_{task_id}_partial.json"),
                        task_id)
                except Exception:
                    pass
                return

        except Exception as e:
            logger.error(f"扫码登录失败: {e}")
            self.login_sessions[task_id]["status"] = "failed"
            self.login_sessions[task_id]["message"] = f"登录失败: {str(e)}"
        finally:
            # 注意：不关闭 browser 和 playwright！
            # 上下文被保持为持久化上下文，浏览器需要继续运行
            pass

    async def _save_context_state(self, context: BrowserContext, task_id: int) -> tuple[str, str]:
        """保存上下文状态到文件，并返回 cookies 备份。"""
        path = str(STORAGE_DIR / f"login_task_{task_id}.json")
        state = await context.storage_state(path=path)
        cookies_json = json.dumps(state.get("cookies", []), ensure_ascii=False)
        logger.info(f"StorageState 已保存: {path}")
        return path, cookies_json

    async def _capture_fingerprint(self, page: Page) -> dict[str, Any]:
        """抓取当前页面的浏览器指纹快照。"""
        browser_fp = await page.evaluate(
            """
            () => ({
              user_agent: navigator.userAgent,
              language: navigator.language,
              languages: navigator.languages,
              platform: navigator.platform,
              hardware_concurrency: navigator.hardwareConcurrency,
              device_memory: navigator.deviceMemory || null,
              device_scale_factor: window.devicePixelRatio || 1,
              color_scheme: window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light',
              timezone_id: Intl.DateTimeFormat().resolvedOptions().timeZone || null,
              viewport: {
                width: window.innerWidth,
                height: window.innerHeight
              },
              screen: {
                width: window.screen.width,
                height: window.screen.height
              }
            })
            """
        )
        browser_fp["locale"] = browser_fp.get("language") or DEFAULT_FINGERPRINT["locale"]
        return browser_fp

    def _update_account_state(
        self,
        account_id: Optional[int],
        storage_path: Optional[str] = None,
        cookies_json: Optional[str] = None
    ) -> None:
        """刷新账号表里的 storage_state / cookies。"""
        if not account_id:
            return

        db = SessionLocal()
        try:
            account = db.query(ScraperAccount).get(account_id)
            if not account:
                return
            if storage_path:
                account.storage_state_path = storage_path
            if cookies_json:
                account.cookies_json = cookies_json
            account.updated_at = datetime.utcnow()
            db.commit()
        except Exception as e:
            logger.warning(f"刷新账号登录态失败: {e}")
            db.rollback()
        finally:
            db.close()

    def _save_account_to_db(
        self,
        task_id: int,
        account_name: str,
        storage_path: str,
        cookies_json: str,
        browser_fingerprint_json: str,
        ua: str | None,
        vp_width: int | None,
        vp_height: int | None,
        account_id: Optional[int] = None
    ) -> Optional[int]:
        """登录成功后写入 ScraperAccount 表，并返回最终账号 ID。"""
        db = SessionLocal()
        try:
            existing = None
            if account_id:
                existing = db.query(ScraperAccount).get(account_id)
            if existing is None:
                existing = db.query(ScraperAccount).filter(
                    ScraperAccount.account_name == account_name
                ).order_by(ScraperAccount.id.desc()).first()

            if existing:
                existing.storage_state_path = storage_path
                existing.user_agent = ua
                existing.viewport_width = vp_width
                existing.viewport_height = vp_height
                existing.login_status = "logged_in"
                existing.last_login_at = datetime.utcnow()
                existing.cookies_json = cookies_json
                existing.browser_fingerprint_json = browser_fingerprint_json
                logger.info(f"更新已有账号记录: id={existing.id}, name={account_name}")
                saved_account = existing
            else:
                saved_account = ScraperAccount(
                    account_name=account_name,
                    login_status="logged_in",
                    storage_state_path=storage_path,
                    user_agent=ua,
                    viewport_width=vp_width,
                    viewport_height=vp_height,
                    last_login_at=datetime.utcnow(),
                    cookies_json=cookies_json,
                    browser_fingerprint_json=browser_fingerprint_json,
                )
                db.add(saved_account)
                logger.info(f"创建新账号记录: name={account_name}")

            # 更新任务状态
            db_task = db.query(ScraperTask).get(task_id)
            if db_task:
                db_task.status = "completed"
                db_task.completed_at = datetime.utcnow()
                if existing:
                    db_task.account_id = existing.id

            db.commit()
            db.refresh(saved_account)
            if db_task and saved_account:
                db_task.account_id = saved_account.id
                db.commit()

            return saved_account.id
        except Exception as e:
            logger.error(f"保存账号记录失败: {e}")
            db.rollback()
            return None
        finally:
            db.close()

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
            "account_name": session.get("account_name"),
            "storage_path": session.get("storage_path"),
            "user_agent": session.get("user_agent"),
            "viewport_width": session.get("viewport_width"),
            "viewport_height": session.get("viewport_height"),
            "message": session.get("message", ""),
        }

    async def check_login_expired(self, context: BrowserContext) -> bool:
        """检查登录是否过期（访问大屏页判断）"""
        page = await context.new_page()
        try:
            test_url = f"{LEADS_BASE}/pc/analysis/live-screen?room_id=check"
            await page.goto(test_url, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(2)

            if "login" in page.url.lower() or "/auth/" in page.url:
                return True

            body = await page.evaluate("document.body?.innerText || ''")
            if "手机登录" in body or "邮箱登录" in body:
                return True

            return False
        except Exception as e:
            logger.warning(f"检查登录状态异常: {e}")
            return True
        finally:
            await page.close()

    async def close(self):
        """关闭浏览器（释放所有资源）"""
        self._logged_in_context = None
        self._logged_in_account_id = None
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        logger.info("浏览器实例已关闭")


# 全局单例
browser_manager = BrowserManager()
