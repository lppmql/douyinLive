"""
采集账号数据访问层 — 从 browser.py 抽取的数据库操作

所有函数接受 db: Session 作为第一个参数，由调用方负责会话生命周期。
这样 browser.py 不再直接操作数据库，也方便独立测试。
"""
import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.logger import logger
from app.core.status import TaskStatus
from app.models.scraper_accounts import ScraperAccount
from app.models.scraper_tasks import ScraperTask
from app.services.tasks.runtime import publish_task_event, touch_task


def find_account_by_storage_path(db: Session, storage_state_path: Optional[str]) -> Optional[ScraperAccount]:
    """通过 storage_state_path 查找账号。"""
    if not storage_state_path:
        return None
    return (
        db.query(ScraperAccount)
        .filter(ScraperAccount.storage_state_path == storage_state_path)
        .order_by(ScraperAccount.id.desc())
        .first()
    )


def find_account_by_id(db: Session, account_id: Optional[int]) -> Optional[ScraperAccount]:
    """通过账号 ID 查找账号。"""
    if not account_id:
        return None
    return db.get(ScraperAccount, account_id)


def find_latest_logged_in_account(db: Session) -> Optional[ScraperAccount]:
    """查找最近登录且登录状态文件仍存在的采集账号。"""
    return (
        db.query(ScraperAccount)
        .filter(
            ScraperAccount.login_status == "logged_in",
            ScraperAccount.storage_state_path.isnot(None),
        )
        .order_by(ScraperAccount.last_login_at.desc().nullslast())
        .first()
    )


def load_account_fingerprint(account: Optional[ScraperAccount]) -> dict[str, Any]:
    """从账号记录中解析浏览器指纹（纯函数，不访问数据库）。

    优先使用 browser_fingerprint_json 字段，回退到 user_agent/viewport 字段。
    """
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
                "width": account.viewport_width or 1920,
                "height": account.viewport_height or 1080,
            },
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            "device_scale_factor": 1,
            "color_scheme": "light",
        }
    return {}


def update_account_state(
    db: Session,
    account_id: Optional[int],
    storage_path: Optional[str] = None,
    cookies_json: Optional[str] = None,
) -> None:
    """刷新账号表里的 storage_state / cookies。"""
    if not account_id:
        return

    account = db.query(ScraperAccount).get(account_id)
    if not account:
        return
    if storage_path:
        account.storage_state_path = storage_path
    if cookies_json:
        account.cookies_json = cookies_json
    account.updated_at = datetime.utcnow()
    # 注意：不在此处 commit，由调用方统一管理事务边界


def save_account_to_db(
    db: Session,
    task_id: int,
    account_name: str,
    storage_path: str,
    cookies_json: str,
    browser_fingerprint_json: str,
    ua: str | None,
    vp_width: int | None,
    vp_height: int | None,
    account_id: Optional[int] = None,
) -> Optional[int]:
    """登录成功后写入 ScraperAccount 表，并返回最终账号 ID。

    如果 account_id 已存在则更新，否则按 account_name 查找或新建。
    """
    existing = None
    if account_id:
        existing = db.query(ScraperAccount).get(account_id)
    if existing is None:
        existing = (
            db.query(ScraperAccount)
            .filter(ScraperAccount.account_name == account_name)
            .order_by(ScraperAccount.id.desc())
            .first()
        )

    if existing:
        existing.storage_state_path = storage_path
        existing.user_agent = ua
        existing.viewport_width = vp_width
        existing.viewport_height = vp_height
        existing.login_status = "logged_in"
        existing.last_login_at = datetime.utcnow()
        existing.cookies_json = cookies_json
        existing.browser_fingerprint_json = browser_fingerprint_json
        saved_account = existing
        logger.info("更新已有账号 account_id=%s name=%s", saved_account.id, account_name)
    else:
        saved_account = ScraperAccount(
            account_name=account_name,
            login_status="logged_in",
            last_login_at=datetime.utcnow(),
            storage_state_path=storage_path,
            cookies_json=cookies_json,
            browser_fingerprint_json=browser_fingerprint_json,
            user_agent=ua,
            viewport_width=vp_width,
            viewport_height=vp_height,
        )
        db.add(saved_account)
        db.flush()
        logger.info("新建采集账号 account_id=%s name=%s", saved_account.id, account_name)

    # 同时更新关联的登录任务（设置 account_id，但不改状态——由调用方处理）
    db_task = db.query(ScraperTask).get(task_id)
    if db_task:
        db_task.account_id = saved_account.id
        touch_task(db_task)

    # 注意：不在此处 commit，由调用方统一管理事务边界
    db.flush()
    db.refresh(saved_account)
    return saved_account.id


def finish_login_task(
    db: Session,
    task_id: int,
    status: str,
    error_message: str | None = None,
) -> None:
    """可靠结束扫码任务，防止异常后任务永久停留在 running。"""
    task = db.get(ScraperTask, task_id)
    if not task or task.status == TaskStatus.COMPLETED:
        return
    task.status = status
    task.completed_at = datetime.utcnow()
    task.error_message = error_message[:500] if error_message else None
    touch_task(task)
    # 注意：不在此处 commit，由调用方统一管理事务边界
    db.flush()
    publish_task_event(
        "scraper",
        task,
        TaskStatus.FAILED if status == TaskStatus.FAILED else status,
        {"task_type": "login", "error": task.error_message or ""},
    )
