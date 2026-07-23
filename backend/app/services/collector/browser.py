"""
浏览器管理器 — 单例模式管理 Playwright Chromium 实例

核心设计：
1. 登录上下文持久化 — 登录成功后保持浏览器上下文不关闭，后续采集复用同一会话
2. 指纹一致性 — 固定 User-Agent、Viewport、浏览器参数，不被平台检测为不同设备
3. Cookie 自动刷新 — 每次采集后保存最新 StorageState，下次可恢复
4. 登录态检测 — 每次采集前验证 Cookie 是否仍然有效
"""
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from app.core.config import settings
from app.core.logger import logger
from app.core.database import SessionLocal
from app.core.status import TaskStatus
from app.models.scraper_accounts import ScraperAccount
from app.models.scraper_tasks import ScraperTask
from app.services.collector.account_repo import (
    find_account_by_id,
    find_account_by_storage_path,
    find_latest_logged_in_account,
    finish_login_task,
    load_account_fingerprint as _load_fingerprint,
    save_account_to_db,
    update_account_state,
)
from app.services.collector.account_identity import fetch_account_identity
from app.services.collector.browser_session import BrowserLeaseKind, BrowserSessionCoordinator
from app.services.collector.constants import LEADS_BASE, DEFAULT_FINGERPRINT
from app.services.tasks.runtime import touch_task, publish_task_event

# 浏览器状态存储目录
STORAGE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "storage_state"
STORAGE_DIR.mkdir(exist_ok=True)

LOGIN_URL = f"{LEADS_BASE}/pc/auth/login"

# 浏览器启动参数
BROWSER_CHANNEL = "chromium"
BROWSER_ARGS = [
    "--headless=new",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    # 采集只依赖接口与 DOM，关闭硬件 GPU 和 WebGL 以降低资源占用；必须保留
    # Chromium 软件光栅器作为无头渲染后备，否则 macOS 图形进程可能 SIGSEGV。
    "--disable-gpu",
    "--disable-webgl",
    "--disable-accelerated-2d-canvas",
    "--log-level=3",
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
            cls._instance._browser_lock = asyncio.Lock()
            cls._instance._context_lock = asyncio.Lock()
            cls._instance._session_coordinator = BrowserSessionCoordinator()
        return cls._instance

    def session_lease(self, owner: str, *, kind: BrowserLeaseKind = "maintenance"):
        """所有复用 Cookie 的页面操作都必须从这里领取独占会话。"""
        return self._session_coordinator.lease(owner, kind=kind)

    def session_snapshot(self) -> dict[str, str | int | None]:
        """返回当前浏览器被谁使用及刷新等待数量。"""
        return self._session_coordinator.snapshot()

    @staticmethod
    def _observe_playwright_transport(playwright) -> None:
        """读取 Playwright 驱动退出结果，避免终端信号留下无人接收的 Future。"""
        try:
            error_future = playwright._impl_obj._connection._transport.on_error_future
        except AttributeError:
            return

        def consume_result(future):
            if future.cancelled():
                return
            try:
                error = future.exception()
            except asyncio.CancelledError:
                return
            if error:
                # 业务页面操作会单独记录真正的采集错误；这个 Future 仅表示驱动管道已关闭。
                logger.debug("Playwright 驱动管道已结束: %s", error)

        error_future.add_done_callback(consume_result)

    async def wait_until_session_idle(self, timeout_seconds: float = 15) -> bool:
        """等待共享登录会话空闲，供安全关闭浏览器使用。"""
        return await self._session_coordinator.wait_until_idle(timeout_seconds)

    async def ensure_browser(self) -> Browser:
        """获取或创建浏览器实例（固定参数）"""
        async with self._browser_lock:
            if self._browser is None or not self._browser.is_connected():
                if self._playwright:
                    try:
                        await self._playwright.stop()
                    except Exception:
                        pass
                self._playwright = await async_playwright().start()
                self._observe_playwright_transport(self._playwright)
                self._browser = await self._playwright.chromium.launch(
                    headless=settings.PLAYWRIGHT_HEADLESS,
                    channel=BROWSER_CHANNEL,
                    args=BROWSER_ARGS,
                )
                logger.info("浏览器实例已创建（Chromium 新版无头模式，图形加速已关闭）")
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
        """从账号记录中解析浏览器指纹（委托给 account_repo）。"""
        return _load_fingerprint(account)

    def _find_account_by_storage_path(self, storage_state_path: Optional[str]) -> Optional[ScraperAccount]:
        """通过 storage_state_path 查找账号。"""
        if not storage_state_path:
            return None
        db = SessionLocal()
        try:
            return find_account_by_storage_path(db, storage_state_path)
        finally:
            db.close()

    def _find_account_by_id(self, account_id: Optional[int]) -> Optional[ScraperAccount]:
        """通过账号 ID 查找账号。"""
        if not account_id:
            return None
        db = SessionLocal()
        try:
            return find_account_by_id(db, account_id)
        finally:
            db.close()

    def _find_latest_logged_in_account(self) -> Optional[ScraperAccount]:
        """查找最近登录且 storage_state 文件仍存在的采集账号。"""
        db = SessionLocal()
        try:
            account = find_latest_logged_in_account(db)
            # 额外验证 storage_state 文件确实存在（磁盘检查，非 DB 问题）
            if account and account.storage_state_path and Path(account.storage_state_path).is_file():
                return account
            return None
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
        # 完整 Chromium 的新版无头模式在上下文零页面时可能退出。保留一个不访问
        # 网络的空白页，业务页面仍按任务创建和关闭，避免下一轮采集拿到关闭的上下文。
        await context.new_page()
        return context

    async def get_logged_in_context(self) -> tuple[Optional[BrowserContext], bool, str]:
        """串行获取或恢复登录上下文，避免并发请求重复创建和相互覆盖。"""
        async with self._context_lock:
            return await self._get_logged_in_context_unlocked()

    async def _get_logged_in_context_unlocked(self) -> tuple[Optional[BrowserContext], bool, str]:
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

                # 浏览器进程断开后旧 Browser 对象也不能继续创建上下文。
                if self._browser and not self._browser.is_connected():
                    self._browser = None

        # 没有持久化上下文，从 StorageState 文件恢复
        if not self._logged_in_storage_path:
            account = self._find_latest_logged_in_account()
            if not account:
                return None, False, "没有可恢复的登录账号，请重新扫码"
            self._logged_in_account_id = account.id
            self._logged_in_storage_path = account.storage_state_path
            logger.info("已从数据库恢复采集账号引用: account_id=%s", account.id)

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

    def invalidate_logged_in_context(self, context: Optional[BrowserContext] = None) -> None:
        """清除失效登录上下文，保留 Cookie 路径供下一次自动恢复。"""
        if context is None or self._logged_in_context is context:
            self._logged_in_context = None

    async def check_account_health(self, account: ScraperAccount) -> tuple[bool, str]:
        """使用账号保存的 Cookie 与指纹做隔离的轻量登录态检查。"""
        async with self.session_lease(f"account-health:{account.id}", kind="account"):
            return await self._check_account_health_unlocked(account)

    async def _check_account_health_unlocked(self, account: ScraperAccount) -> tuple[bool, str]:
        """已取得浏览器会话租约后的真实 Cookie 检查。"""
        if not account.storage_state_path or not Path(account.storage_state_path).is_file():
            return False, "未找到账号登录状态文件，请重新扫码"

        context = await self.create_context(
            account.storage_state_path,
            self._load_account_fingerprint(account),
        )
        try:
            expired = await self.check_login_expired(context)
            if not expired:
                identity = await fetch_account_identity(context)
                if identity.get("douyin_nickname"):
                    account.douyin_nickname = identity["douyin_nickname"]
                if identity.get("douyin_id"):
                    account.douyin_id = identity["douyin_id"]
                try:
                    # 存活检查可能收到平台轮换的新 Cookie，验证成功后立即落盘，
                    # 后续采集继续使用同一套 Cookie 和浏览器指纹，不需要重新扫码。
                    state = await context.storage_state(path=account.storage_state_path)
                    Path(account.storage_state_path).chmod(0o600)
                    account.cookies_json = json.dumps(state.get("cookies", []), ensure_ascii=False)
                    account.cookie_refreshed_at = datetime.utcnow()
                except Exception as exc:
                    # Cookie 已经通过真实页面验证，落盘失败只记录告警，不能误判账号失效。
                    logger.warning("账号 Cookie 刷新保存失败 account_id=%s: %s", account.id, exc)
            return (False, "Cookie 已失效，请重新扫码") if expired else (True, "账号登录状态有效")
        except Exception as exc:
            logger.warning("账号存活检查失败 account_id=%s: %s", account.id, exc)
            return False, "账号检查失败，请稍后重试"
        finally:
            await context.close()

    async def set_logged_in_context(self, context: BrowserContext, storage_path: str, account_id: int):
        """串行替换登录上下文，避免扫码完成时关闭正在恢复的上下文。"""
        async with self.session_lease(f"login-replace:{account_id}", kind="login"):
            async with self._context_lock:
                await self._set_logged_in_context_unlocked(context, storage_path, account_id)

    async def _set_logged_in_context_unlocked(
        self,
        context: BrowserContext,
        storage_path: str,
        account_id: int,
    ) -> None:
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
        async with self.session_lease("cookie-refresh", kind="account"):
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
        """扫码期间独占共享浏览器，避免监控或刷新与登录页面争抢账号状态。"""
        async with self.session_lease(f"qr-login:{task_id}", kind="login"):
            await self._qr_login_worker_serialized(task_id, account_name, account_id)

    async def _qr_login_worker_serialized(
        self,
        task_id: int,
        account_name: str,
        account_id: Optional[int] = None,
    ):
        """在浏览器租约内完成二维码登录并把上下文交给统一管理器。"""
        browser = None
        context = None
        context_adopted = False
        try:
            self.login_sessions[task_id]["status"] = "scanning"
            self.login_sessions[task_id]["message"] = "正在打开浏览器..."

            browser = await self.ensure_browser()

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
                self.login_sessions[task_id]["status"] = TaskStatus.FAILED
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
                identity = await fetch_account_identity(context)
                ua = fingerprint_snapshot.get("user_agent")
                vp = fingerprint_snapshot.get("viewport") or {}

                self.login_sessions[task_id].update({
                    "storage_path": storage_path,
                    "cookies_json": cookies_json,
                    "browser_fingerprint_json": json.dumps(fingerprint_snapshot, ensure_ascii=False),
                    "user_agent": ua,
                    "viewport_width": vp.get("width") if vp else None,
                    "viewport_height": vp.get("height") if vp else None,
                    "douyin_nickname": identity.get("douyin_nickname"),
                    "douyin_id": identity.get("douyin_id"),
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
                    douyin_nickname=identity.get("douyin_nickname"),
                    douyin_id=identity.get("douyin_id"),
                )
                self.login_sessions[task_id]["account_id"] = saved_account_id

                # 将登录上下文设置为持久化上下文（不关闭浏览器！）
                async with self._context_lock:
                    await self._set_logged_in_context_unlocked(
                        context,
                        storage_path,
                        saved_account_id or task_id,
                    )
                context_adopted = True
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
                self._finish_login_task(task_id, TaskStatus.FAILED, "扫码登录超时，请重新扫码")
                # 即使超时也保存上下文（可能部分登录成功）
                try:
                    async with self._context_lock:
                        await self._set_logged_in_context_unlocked(
                            context,
                            str(STORAGE_DIR / f"login_task_{task_id}_partial.json"),
                            task_id,
                        )
                    context_adopted = True
                except Exception:
                    pass
                return

        except Exception as e:
            logger.error(f"扫码登录失败: {e}")
            self.login_sessions[task_id]["status"] = TaskStatus.FAILED
            self.login_sessions[task_id]["message"] = f"登录失败: {str(e)}"
            self._finish_login_task(task_id, TaskStatus.FAILED, f"扫码登录失败: {str(e)}")
        finally:
            # 成功或部分成功的登录上下文由统一管理器继续复用；失败页面必须立即释放。
            if context and not context_adopted:
                try:
                    await context.close()
                except Exception:
                    pass

    async def _save_context_state(self, context: BrowserContext, task_id: int) -> tuple[str, str]:
        """保存上下文状态到文件，并返回 cookies 备份。"""
        path = str(STORAGE_DIR / f"login_task_{task_id}.json")
        state = await context.storage_state(path=path)
        # Cookie 与指纹属于登录凭据，只允许当前系统用户读写。
        Path(path).chmod(0o600)
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
        """刷新账号表里的 storage_state / cookies（委托给 account_repo）。"""
        if not account_id:
            return
        db = SessionLocal()
        try:
            update_account_state(db, account_id, storage_path, cookies_json)
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
        account_id: Optional[int] = None,
        douyin_nickname: str | None = None,
        douyin_id: str | None = None,
    ) -> Optional[int]:
        """登录成功后写入 ScraperAccount 表，并返回最终账号 ID。

        委托 account_repo.save_account_to_db 处理数据持久化。
        """
        db = SessionLocal()
        try:
            saved_id = save_account_to_db(
                db, task_id, account_name, storage_path,
                cookies_json, browser_fingerprint_json,
                ua, vp_width, vp_height, account_id,
                douyin_nickname, douyin_id,
            )
            # 登录成功后同时将关联任务标记为完成
            if saved_id:
                db_task = db.query(ScraperTask).get(task_id)
                if db_task:
                    db_task.status = TaskStatus.COMPLETED
                    db_task.completed_at = datetime.utcnow()
                    db_task.error_message = None
                    touch_task(db_task)
                    db.commit()
                    publish_task_event(
                        "scraper", db_task, TaskStatus.COMPLETED,
                        {"task_type": "login", "account_id": saved_id},
                    )
            return saved_id
        except Exception as e:
            logger.error(f"保存账号记录失败: {e}")
            db.rollback()
            return None
        finally:
            db.close()

    def _finish_login_task(self, task_id: int, status: str, error_message: str | None = None) -> None:
        """可靠结束扫码任务（委托给 account_repo）。"""
        db = SessionLocal()
        try:
            finish_login_task(db, task_id, status, error_message)
        except Exception as exc:
            db.rollback()
            logger.warning("扫码任务状态更新失败 task_id=%s: %s", task_id, exc)
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
            "douyin_nickname": session.get("douyin_nickname"),
            "douyin_id": session.get("douyin_id"),
            "message": session.get("message", ""),
        }

    async def check_login_expired(self, context: BrowserContext) -> bool:
        """连续两次访问都显示登录页时才判过期，过滤平台临时跳转。"""
        test_url = f"{LEADS_BASE}/pc/analysis/live-screen?room_id=check"
        for attempt in range(2):
            page = await context.new_page()
            try:
                await page.goto(test_url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2)
                body = await page.evaluate("document.body?.innerText || ''")
                expired = (
                    "login" in page.url.lower()
                    or "/auth/" in page.url
                    or "手机登录" in body
                    or "邮箱登录" in body
                )
                if not expired:
                    return False
                logger.warning("登录态探测疑似过期，正在复核 (attempt=%s)", attempt + 1)
            except Exception as exc:
                logger.warning("检查登录状态异常 (attempt=%s): %s", attempt + 1, exc)
            finally:
                await page.close()

            if attempt == 0:
                await asyncio.sleep(1)

        return True

    async def close(self):
        """按页面、上下文、浏览器、驱动的顺序关闭，确保异步响应完整收尾。"""
        async with self.session_lease("browser-close", kind="maintenance"):
            async with self._context_lock:
                async with self._browser_lock:
                    browser = self._browser
                    contexts = list(browser.contexts) if browser and browser.is_connected() else []

                    self._logged_in_context = None
                    self._logged_in_account_id = None
                    self._logged_in_storage_path = None

                    # 直接 browser.close() 会让仍在读取响应的页面同时断线。先逐层关闭，
                    # Playwright 才能把每个 Future 的结果交还给调用方，而不是在退出后报噪声。
                    for context in contexts:
                        for page in list(context.pages):
                            try:
                                await page.close(run_before_unload=False)
                            except Exception:
                                pass
                        try:
                            await context.close()
                        except Exception:
                            pass
                    await asyncio.sleep(0)

                    if self._playwright:
                        try:
                            # stop() 会先给驱动管道设置停止标记，再回收它启动的浏览器。
                            # 此处不再额外 browser.close()，避免同一管道被关闭两次。
                            await self._playwright.stop()
                        except Exception:
                            pass
                    elif browser:
                        try:
                            if browser.is_connected():
                                await browser.close()
                        except Exception:
                            pass
                    self._browser = None
                    self._playwright = None
                    # 让驱动关闭回调在 lifespan 结束前执行，避免“Future exception was never retrieved”。
                    await asyncio.sleep(0)
                    logger.info("浏览器实例已关闭")


# 全局单例
browser_manager = BrowserManager()
