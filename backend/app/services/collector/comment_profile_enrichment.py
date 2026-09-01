"""评论用户公开资料分级补全服务。

服务只读取用户提供的独立 Cookie 文件和固定请求指纹，不接触企业后台账号、
扫码 Cookie 或浏览器上下文。日志只记录任务数量和脱敏错误代码。
"""

from __future__ import annotations

import asyncio
import stat
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import and_, func, or_

from app.core.config import PROJECT_ROOT, settings
from app.core.database import SessionLocal
from app.core.logger import logger
from app.models.comment_user_profiles import CommentUserProfile
from app.models.comments import Comment


PROFILE_URL = "https://www.iesdouyin.com/web/api/v2/user/info/"
RETRY_DELAYS = (timedelta(hours=1), timedelta(hours=6), timedelta(hours=24))


def _cookie_file_path() -> Path:
    """把相对路径固定解析到项目根目录，避免受启动目录影响。"""
    configured = Path(settings.DOUYIN_PROFILE_COOKIE_FILE).expanduser()
    return configured if configured.is_absolute() else PROJECT_ROOT / configured


def profile_configuration_status() -> dict[str, Any]:
    """只返回配置是否可用，不暴露 Cookie、路径或完整指纹。"""
    cookie_path = _cookie_file_path()
    try:
        private_mode = (
            cookie_path.is_file()
            and stat.S_IMODE(cookie_path.stat().st_mode) & 0o077 == 0
        )
        readable = private_mode and bool(cookie_path.read_text(errors="ignore").strip())
    except OSError:
        private_mode = False
        readable = False
    return {
        "configured": readable,
        "cookie_file_secure": private_mode,
        "fingerprint_configured": bool(
            settings.DOUYIN_PROFILE_USER_AGENT and settings.DOUYIN_PROFILE_SEC_CH_UA
        ),
        "batch_size": settings.DOUYIN_PROFILE_BATCH_SIZE,
        "request_interval_seconds": settings.DOUYIN_PROFILE_REQUEST_INTERVAL_SECONDS,
    }


def _load_cookie_header() -> str:
    """读取 Cookie 文件并过滤前置域名；任何日志都不得输出返回值。"""
    path = _cookie_file_path()
    if not path.is_file():
        raise RuntimeError("PROFILE_COOKIE_FILE_MISSING")
    pairs = []
    for item in path.read_text(errors="replace").replace("\n", ";").split(";"):
        item = item.strip()
        if "=" not in item:
            continue
        name, value = item.split("=", 1)
        name = name.strip()
        if name and all(char.isalnum() or char in "_-." for char in name):
            pairs.append(f"{name}={value.strip()}")
    if not pairs:
        raise RuntimeError("PROFILE_COOKIE_INVALID")
    return "; ".join(pairs)


def _request_headers(cookie: str) -> dict[str, str]:
    """生成与用户 Cookie 配套的稳定请求指纹。"""
    return {
        "accept": "application/json,text/plain,*/*",
        "accept-language": f"{settings.DOUYIN_PROFILE_LOCALE},zh;q=0.9,en;q=0.8",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "referer": "https://www.douyin.com/",
        "sec-ch-ua": settings.DOUYIN_PROFILE_SEC_CH_UA,
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": f'"{settings.DOUYIN_PROFILE_PLATFORM}"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": settings.DOUYIN_PROFILE_USER_AGENT,
        "cookie": cookie,
    }


def _first_https_avatar(user: dict[str, Any]) -> str | None:
    """从多尺寸头像中选择首个真实 HTTPS 地址。"""
    for key in ("avatar_medium", "avatar_thumb", "avatar_larger"):
        value = user.get(key) or {}
        urls = (
            value.get("url_list") or value.get("urlList") or []
            if isinstance(value, dict)
            else []
        )
        for url in urls:
            if isinstance(url, str) and url.startswith("https://"):
                return url[:1000]
    return None


async def _fetch_profile(client: httpx.AsyncClient, sec_uid: str) -> dict[str, Any]:
    """获取并严格校验一个用户的真实公开资料。"""
    response = await client.get(PROFILE_URL, params={"sec_uid": sec_uid})
    if response.status_code in {403, 429}:
        raise RuntimeError(f"PROFILE_HTTP_{response.status_code}")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("status_code") != 0:
        raise RuntimeError("PROFILE_API_REJECTED")
    user = payload.get("user_info") or {}
    if not isinstance(user, dict) or user.get("sec_uid") != sec_uid:
        raise RuntimeError("PROFILE_IDENTITY_MISMATCH")
    unique_id = str(user.get("unique_id") or "").strip()[:100] or None
    short_id = str(user.get("short_id") or "").strip()[:100] or None
    return {
        "nickname": str(user.get("nickname") or "").strip()[:100] or None,
        "avatar_url": _first_https_avatar(user),
        "unique_id": unique_id,
        "short_id": short_id,
        "public_douyin_id": unique_id or short_id,
        "douyin_id_type": "unique_id"
        if unique_id
        else "short_id"
        if short_id
        else None,
    }


def _candidate_sec_uids(
    session_id: int | None,
    force: bool,
    limit: int | None = None,
) -> list[str]:
    """高意向优先、最近评论优先生成去重候选，不加载评论正文。"""
    db = SessionLocal()
    try:
        latest = func.max(Comment.id).label("latest_id")
        priority = func.max(Comment.is_high_intent).label("intent_priority")
        query = db.query(Comment.user_sec_uid, latest, priority).filter(
            Comment.user_sec_uid.isnot(None), Comment.user_sec_uid != ""
        )
        if session_id is not None:
            query = query.filter(Comment.session_id == session_id)
        rows = (
            query.group_by(Comment.user_sec_uid)
            .order_by(priority.desc(), latest.desc())
            .all()
        )
        now = datetime.utcnow()
        profiles = {
            item.sec_uid: item
            for item in db.query(CommentUserProfile)
            .filter(CommentUserProfile.sec_uid.in_([row[0] for row in rows]))
            .all()
        }
        fresh_after = now - timedelta(days=settings.DOUYIN_PROFILE_CACHE_DAYS)
        candidates = []
        for sec_uid, *_ in rows:
            profile = profiles.get(sec_uid)
            if profile:
                # 强制刷新只允许绕过成功缓存，平台退避时间永远不能绕过。
                if profile.retry_after and profile.retry_after > now:
                    continue
                if (
                    not force
                    and profile.last_fetched_at
                    and profile.last_fetched_at >= fresh_after
                    and profile.fetch_status in {"success", "partial"}
                ):
                    continue
            candidates.append(sec_uid)
            if limit is not None and len(candidates) >= max(1, limit):
                break
        return candidates
    finally:
        db.close()


def _save_success(sec_uid: str, values: dict[str, Any]) -> None:
    """缓存资料，并同步补齐所有场次中该用户的评论副本。"""
    db = SessionLocal()
    try:
        profile = (
            db.query(CommentUserProfile)
            .filter(CommentUserProfile.sec_uid == sec_uid)
            .first()
        )
        if profile is None:
            profile = CommentUserProfile(sec_uid=sec_uid)
            db.add(profile)
        for field, value in values.items():
            setattr(profile, field, value)
        profile.fetch_status = (
            "success"
            if values.get("avatar_url") and values.get("public_douyin_id")
            else "partial"
        )
        profile.last_fetched_at = datetime.utcnow()
        profile.retry_after = None
        profile.failure_count = 0
        profile.last_error_code = None
        updates: dict[str, Any] = {}
        if values.get("avatar_url"):
            updates["user_avatar_url"] = values["avatar_url"]
        if values.get("public_douyin_id"):
            updates["user_douyin_id"] = values["public_douyin_id"]
        if updates:
            db.query(Comment).filter(Comment.user_sec_uid == sec_uid).update(
                updates, synchronize_session=False
            )
        db.commit()
    finally:
        db.close()


def _sync_cached_profiles_to_comments(session_id: int | None = None) -> int:
    """把已验证的公开资料同步给新评论，回访用户无需再次请求平台。"""
    db = SessionLocal()
    try:
        query = (
            db.query(Comment, CommentUserProfile)
            .join(
                CommentUserProfile,
                CommentUserProfile.sec_uid == Comment.user_sec_uid,
            )
            .filter(
                or_(
                    and_(
                        or_(Comment.user_avatar_url.is_(None), Comment.user_avatar_url == ""),
                        CommentUserProfile.avatar_url.isnot(None),
                        CommentUserProfile.avatar_url != "",
                    ),
                    and_(
                        or_(Comment.user_douyin_id.is_(None), Comment.user_douyin_id == ""),
                        CommentUserProfile.public_douyin_id.isnot(None),
                        CommentUserProfile.public_douyin_id != "",
                    ),
                )
            )
        )
        if session_id is not None:
            query = query.filter(Comment.session_id == session_id)
        rows = query.order_by(Comment.id.asc()).limit(10000).all()
        updated = 0
        for comment, profile in rows:
            changed = False
            if not comment.user_avatar_url and profile.avatar_url:
                comment.user_avatar_url = profile.avatar_url
                changed = True
            if not comment.user_douyin_id and profile.public_douyin_id:
                comment.user_douyin_id = profile.public_douyin_id
                changed = True
            updated += int(changed)
        if updated:
            db.commit()
        return updated
    finally:
        db.close()


def _save_failure(sec_uid: str, code: str, blocked: bool) -> None:
    """只保存脱敏错误代码，并按失败次数延后重试。"""
    db = SessionLocal()
    try:
        profile = (
            db.query(CommentUserProfile)
            .filter(CommentUserProfile.sec_uid == sec_uid)
            .first()
        )
        if profile is None:
            profile = CommentUserProfile(sec_uid=sec_uid)
            db.add(profile)
        profile.failure_count = int(profile.failure_count or 0) + 1
        profile.fetch_status = "blocked" if blocked else "failed"
        delay = RETRY_DELAYS[min(profile.failure_count - 1, len(RETRY_DELAYS) - 1)]
        profile.retry_after = datetime.utcnow() + delay
        profile.last_error_code = code[:50]
        db.commit()
    finally:
        db.close()


class CommentProfileEnrichmentManager:
    """单并发执行资料补全，避免重复任务和突发请求。"""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._automatic_task: asyncio.Task | None = None
        self._blocked_until: datetime | None = None
        self._state: dict[str, Any] = {
            "status": "idle",
            "scope": None,
            "total": 0,
            "completed": 0,
            "success": 0,
            "partial": 0,
            "failed": 0,
            "message": "等待开始",
        }

    def snapshot(self) -> dict[str, Any]:
        cooldown_seconds = (
            max(
                0,
                int((self._blocked_until - datetime.utcnow()).total_seconds()),
            )
            if self._blocked_until
            else 0
        )
        return {
            **self._state,
            **profile_configuration_status(),
            "cooldown_seconds": cooldown_seconds,
        }

    @property
    def automatic_running(self) -> bool:
        """自动发现循环是否仍在运行；不暴露 Cookie 或用户身份。"""
        return bool(self._automatic_task and not self._automatic_task.done())

    async def start_automatic(self) -> None:
        """启动常驻低速发现循环；重复调用保持幂等。"""
        if self.automatic_running:
            return
        self._automatic_task = asyncio.create_task(
            self._automatic_loop(),
            name="comment-profile-enrichment-automatic",
        )
        logger.info("评论用户公开资料后台自动补全已启动")

    async def stop_automatic(self) -> None:
        """应用停机时停止发现循环和正在执行的资料请求。"""
        tasks = [
            task
            for task in (self._automatic_task, self._task)
            if task and not task.done()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._automatic_task = None
        self._task = None

    async def _automatic_loop(self) -> None:
        """定期发现新增用户；配置缺失、任务繁忙和风控冷却均静默等待。"""
        interval = max(30, settings.DOUYIN_PROFILE_AUTO_CHECK_INTERVAL_SECONDS)
        while True:
            try:
                if profile_configuration_status()["configured"]:
                    try:
                        self.start(
                            session_id=None,
                            force=False,
                            candidate_limit=settings.DOUYIN_PROFILE_BATCH_SIZE,
                        )
                    except RuntimeError as exc:
                        if str(exc) not in {
                            "PROFILE_TASK_BUSY",
                            "PROFILE_TASK_COOLDOWN",
                            "PROFILE_COOKIE_NOT_CONFIGURED",
                        }:
                            raise
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - 自动服务失败后按周期自愈
                logger.warning(
                    "评论用户资料自动发现异常，稍后重试: code=%s",
                    type(exc).__name__,
                )
                await asyncio.sleep(interval)

    def start(
        self,
        session_id: int | None = None,
        force: bool = False,
        candidate_limit: int | None = None,
    ) -> dict[str, Any]:
        requested_scope = f"session:{session_id}" if session_id else "all"
        if self._blocked_until and self._blocked_until > datetime.utcnow():
            raise RuntimeError("PROFILE_TASK_COOLDOWN")
        if self._task and not self._task.done():
            if self._state.get("scope") != requested_scope:
                raise RuntimeError("PROFILE_TASK_BUSY")
            return self.snapshot()
        if not profile_configuration_status()["configured"]:
            raise RuntimeError("PROFILE_COOKIE_NOT_CONFIGURED")
        self._state = {
            "status": "starting",
            "scope": requested_scope,
            "total": 0,
            "completed": 0,
            "success": 0,
            "partial": 0,
            "failed": 0,
            "message": "资料补全任务正在启动",
        }
        self._task = asyncio.create_task(
            self._run(session_id, force, candidate_limit),
            name="comment-profile-enrichment",
        )
        return self.snapshot()

    async def _run(
        self,
        session_id: int | None,
        force: bool,
        candidate_limit: int | None = None,
    ) -> None:
        # 回访用户优先复用数据库中已经验证的公开资料，不重复访问平台。
        await asyncio.to_thread(_sync_cached_profiles_to_comments, session_id)
        candidates = _candidate_sec_uids(session_id, force, candidate_limit)
        self._state = {
            "status": "running",
            "scope": f"session:{session_id}" if session_id else "all",
            "total": len(candidates),
            "completed": 0,
            "success": 0,
            "partial": 0,
            "failed": 0,
            "message": "正在按优先级补全评论用户公开资料",
        }
        consecutive_failures = 0
        try:
            cookie = _load_cookie_header()
            headers = _request_headers(cookie)
            timeout = httpx.Timeout(settings.DOUYIN_PROFILE_REQUEST_TIMEOUT_SECONDS)
            async with httpx.AsyncClient(
                headers=headers, timeout=timeout, follow_redirects=True, http2=True
            ) as client:
                for index, sec_uid in enumerate(candidates, 1):
                    try:
                        values = await _fetch_profile(client, sec_uid)
                        await asyncio.to_thread(_save_success, sec_uid, values)
                        is_complete = bool(
                            values.get("avatar_url") and values.get("public_douyin_id")
                        )
                        self._state["success" if is_complete else "partial"] += 1
                        consecutive_failures = 0
                    except Exception as exc:
                        code = (
                            str(exc)
                            if str(exc).startswith("PROFILE_")
                            else type(exc).__name__.upper()
                        )
                        blocked = code in {"PROFILE_HTTP_403", "PROFILE_HTTP_429"}
                        await asyncio.to_thread(_save_failure, sec_uid, code, blocked)
                        self._state["failed"] += 1
                        consecutive_failures += 1
                        if blocked or consecutive_failures >= 5:
                            if blocked:
                                self._blocked_until = datetime.utcnow() + timedelta(
                                    hours=1
                                )
                            self._state.update(
                                status="blocked",
                                message="平台风控或连续失败，任务已安全暂停",
                            )
                            break
                    finally:
                        self._state["completed"] = index
                    await asyncio.sleep(
                        settings.DOUYIN_PROFILE_REQUEST_INTERVAL_SECONDS
                    )
                    if (
                        index < len(candidates)
                        and index % settings.DOUYIN_PROFILE_BATCH_SIZE == 0
                    ):
                        await asyncio.sleep(settings.DOUYIN_PROFILE_BATCH_PAUSE_SECONDS)
            if self._state["status"] == "running":
                self._state.update(
                    status="completed", message="评论用户公开资料补全完成"
                )
        except Exception as exc:
            logger.warning("评论用户资料补全停止: code=%s", type(exc).__name__)
            self._state.update(
                status="failed", message="资料补全启动失败，请检查独立 Cookie 配置"
            )


comment_profile_enrichment_manager = CommentProfileEnrichmentManager()
