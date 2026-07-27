"""从 kezi.lpp6.com 增量同步真实客资。

“增量同步”大白话：服务只从上次成功保存的编号继续往后拉，不会每分钟
把全部历史数据重读一遍。每条数据还会保存源系统唯一编号，双重保证不重复。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import is_valid_kezi_api_key, settings
from app.core.logger import logger
from app.models.lead_sync_states import LeadSyncState
from app.models.leads import Lead
from app.models.live_sessions import LiveSession


SOURCE_SYSTEM = "kezi"
_SYNC_LOCK = asyncio.Lock()
_SHANGHAI = ZoneInfo("Asia/Shanghai")


class KeziSyncError(RuntimeError):
    """可以安全展示给管理员的同步错误，不包含响应正文或数据库参数。"""


class KeziLeadItem(BaseModel):
    """客资服务返回的单条真实记录。"""

    model_config = ConfigDict(populate_by_name=True)

    source_id: int = Field(alias="sourceId", gt=0)
    phone: str = Field(default="", max_length=20)
    douyin_id: str = Field(default="", alias="douyinId", max_length=100)
    anchor: str = Field(default="", max_length=100)
    created_at: datetime = Field(alias="createdAt")

    @field_validator("phone", "douyin_id", "anchor", mode="before")
    @classmethod
    def clean_text(cls, value):
        """接口必须返回字符串；拒绝悄悄把对象或数字变成脏数据。"""
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError("客资文本字段必须是字符串")
        return value.strip()

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        """数据库使用上海本地无时区时间，入库前统一到同一把尺子。"""
        if value.tzinfo is None:
            return value
        return value.astimezone(_SHANGHAI).replace(tzinfo=None)


class KeziLeadPage(BaseModel):
    """客资服务的一页增量结果。"""

    model_config = ConfigDict(populate_by_name=True)

    last_id: int = Field(alias="lastId", ge=0)
    count: int = Field(ge=0)
    has_more: bool = Field(alias="hasMore")
    data: list[KeziLeadItem]


class KeziLeadClient:
    """只在后端持有密钥的客资查询客户端，浏览器永远接触不到密钥。"""

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or settings.KEZI_BASE_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.KEZI_API_KEY

    async def fetch_page(self, last_id: int, limit: int) -> KeziLeadPage:
        """拉取一页数据；错误信息不包含响应正文，避免把手机号写进日志。"""
        if not is_valid_kezi_api_key(self.api_key):
            raise KeziSyncError("客资查询密钥未配置，请在项目根目录 .env 设置 KEZI_API_KEY")
        headers = {
            # 同时兼容当前 x-api-key 服务和新版 Bearer 服务，便于平滑部署。
            "x-api-key": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
        }
        timeout = httpx.Timeout(settings.KEZI_REQUEST_TIMEOUT_SECONDS)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/douyinhao",
                    params={"lastId": last_id, "limit": limit},
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            raise KeziSyncError("客资服务连接失败或请求超时") from exc
        if response.status_code != 200:
            raise KeziSyncError(f"客资服务查询失败，HTTP {response.status_code}")
        try:
            page = KeziLeadPage.model_validate(response.json())
        except ValueError as exc:
            raise KeziSyncError("客资服务返回格式不符合增量同步协议") from exc
        validate_page_cursor(page, last_id)
        return page


def validate_page_cursor(page: KeziLeadPage, last_id: int) -> None:
    """整页契约校验通过后才能推进游标，防止乱序数据造成漏拉或死循环。"""
    if page.count != len(page.data):
        raise KeziSyncError("客资服务返回的 count 与 data 条数不一致")
    source_ids = [item.source_id for item in page.data]
    if any(source_id <= last_id for source_id in source_ids):
        raise KeziSyncError("客资服务返回了不大于当前游标的 sourceId")
    if any(current <= previous for previous, current in zip(source_ids, source_ids[1:])):
        raise KeziSyncError("客资服务返回的 sourceId 没有严格递增")
    if page.data and page.last_id != page.data[-1].source_id:
        raise KeziSyncError("客资服务返回的 lastId 与最后一条 sourceId 不一致")
    if not page.data and page.last_id != last_id:
        raise KeziSyncError("客资服务空页不能推进 lastId")


def _state(db: Session) -> LeadSyncState:
    """读取或建立唯一同步游标。"""
    state = db.query(LeadSyncState).filter(LeadSyncState.source_system == SOURCE_SYSTEM).first()
    if state is None:
        state = LeadSyncState(source_system=SOURCE_SYSTEM, last_external_id=0)
        db.add(state)
        db.flush()
    return state


def match_live_session(db: Session, item: KeziLeadItem) -> LiveSession | None:
    """按真实主播名和直播时间窗匹配场次，没有证据时返回 None。"""
    if not item.anchor:
        return None
    candidates = (
        db.query(LiveSession)
        .filter(
            or_(
                LiveSession.anchor_name == item.anchor,
                LiveSession.anchor_nickname == item.anchor,
            ),
            LiveSession.live_start_time.isnot(None),
            LiveSession.live_start_time <= item.created_at,
        )
        .order_by(LiveSession.live_start_time.desc(), LiveSession.id.desc())
        .all()
    )
    covered_sessions: list[LiveSession] = []
    for session in candidates:
        end_time = session.live_end_time
        if end_time is None and int(session.live_duration_seconds or 0) > 0:
            end_time = session.live_start_time + timedelta(seconds=int(session.live_duration_seconds))
        if end_time is None and session.live_status == "live":
            end_time = datetime.now(_SHANGHAI).replace(tzinfo=None) + timedelta(minutes=5)
        if end_time is not None and item.created_at <= end_time:
            covered_sessions.append(session)
    # 同名主播或重复场次导致两个时间窗同时覆盖时，没有足够证据选择其中之一。
    # 宁可进入待归属，也不能按“最新 ID”猜测。
    return covered_sessions[0] if len(covered_sessions) == 1 else None


def _save_item(db: Session, item: KeziLeadItem) -> tuple[bool, int | None]:
    """幂等保存一条客资，返回“是否新增”和匹配到的场次编号。"""
    existing = (
        db.query(Lead)
        .filter(
            Lead.external_source == SOURCE_SYSTEM,
            Lead.external_id == item.source_id,
        )
        .first()
    )
    if existing:
        return False, existing.session_id

    session = match_live_session(db, item)
    lead = Lead(
        session_id=session.id if session else None,
        lead_phone=item.phone or None,
        douyin_id=item.douyin_id or None,
        anchor_name=item.anchor or None,
        lead_source="抖音站内私信",
        external_source=SOURCE_SYSTEM,
        external_id=item.source_id,
        attribution_status="matched" if session else "pending",
        is_valid=1,
        create_time=item.created_at,
        remark=None if session else "未找到同主播且时间覆盖的真实直播场次，等待人工归属",
    )
    db.add(lead)
    return True, session.id if session else None


def _refresh_session_lead_counts(db: Session, session_ids: set[int]) -> None:
    """只更新本轮受影响场次，避免每次同步扫描全部历史数据。"""
    # 新客资刚加入 Session 但尚未提交，先 flush 才能让下面的 COUNT 看见它。
    db.flush()
    for session_id in session_ids:
        session = db.get(LiveSession, session_id)
        if session is None:
            continue
        session.leads_count = (
            db.query(Lead.id)
            .filter(
                Lead.session_id == session_id,
                Lead.is_valid == 1,
            )
            .count()
        )


async def sync_kezi_leads(
    db: Session,
    *,
    client: KeziLeadClient | None = None,
    max_pages: int = 20,
) -> dict:
    """顺序拉取并提交每一页；只有成功入库后才推进游标。"""
    client = client or KeziLeadClient()
    async with _SYNC_LOCK:
        state = _state(db)
        state.status = "running"
        state.last_error = None
        db.commit()
        added = 0
        duplicates = 0
        matched = 0
        pending = 0
        pages = 0
        try:
            while pages < max(1, max_pages):
                page = await client.fetch_page(
                    int(state.last_external_id or 0),
                    settings.KEZI_SYNC_PAGE_SIZE,
                )
                page_added = 0
                page_duplicates = 0
                affected_session_ids: set[int] = set()
                for item in page.data:
                    created, session_id = _save_item(db, item)
                    if created:
                        added += 1
                        page_added += 1
                        if session_id:
                            matched += 1
                            affected_session_ids.add(session_id)
                        else:
                            pending += 1
                    else:
                        duplicates += 1
                        page_duplicates += 1

                _refresh_session_lead_counts(db, affected_session_ids)
                state.last_external_id = page.last_id
                state.synced_count = int(state.synced_count or 0) + page_added
                state.duplicate_count = int(state.duplicate_count or 0) + page_duplicates
                state.pending_count = db.query(Lead.id).filter(
                    Lead.external_source == SOURCE_SYSTEM,
                    Lead.attribution_status == "pending",
                ).count()
                state.last_synced_at = datetime.utcnow()
                state.status = "completed"
                db.commit()
                pages += 1
                if not page.has_more or not page.data:
                    break

            logger.info(
                "客资增量同步完成：新增 %s 条，重复 %s 条，已归属 %s 条，待归属 %s 条",
                added,
                duplicates,
                matched,
                pending,
            )
            return {
                "success": True,
                "added_count": added,
                "duplicate_count": duplicates,
                "matched_count": matched,
                # 前端展示系统当前仍需人工处理的总数，而不是“本轮新增待归属数”。
                "pending_count": int(state.pending_count or 0),
                "last_external_id": int(state.last_external_id or 0),
                "page_count": pages,
            }
        except Exception as exc:
            db.rollback()
            safe_error = (
                str(exc)
                if isinstance(exc, KeziSyncError)
                else "客资同步内部错误，未推进游标，请稍后重试"
            )
            state = _state(db)
            state.status = "failed"
            state.last_error = safe_error
            db.commit()
            raise KeziSyncError(safe_error) from exc


class KeziLeadSyncManager:
    """独立的小型定时器，不占用浏览器、ASR 或 DataEase 的任务队列。"""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    @property
    def running(self) -> bool:
        return bool(self._task and not self._task.done())

    async def start(self) -> None:
        """只有配置了合格密钥才启动，未配置时主系统其他功能照常可用。"""
        if self.running or not is_valid_kezi_api_key(settings.KEZI_API_KEY):
            if not is_valid_kezi_api_key(settings.KEZI_API_KEY):
                logger.warning("客资增量同步尚未启动：请在根目录 .env 配置 KEZI_API_KEY")
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="kezi-lead-sync")
        logger.info("客资增量同步已启动，每 %s 秒检查一次", settings.KEZI_SYNC_INTERVAL_SECONDS)

    async def stop(self) -> None:
        """安全停止定时器；正在提交的一页会先完成数据库事务。"""
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def _run(self) -> None:
        from app.core.database import SessionLocal

        while not self._stop_event.is_set():
            db = SessionLocal()
            try:
                await sync_kezi_leads(db)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                safe_error = (
                    str(exc)
                    if isinstance(exc, KeziSyncError)
                    else "客资同步内部错误，未推进游标，请稍后重试"
                )
                logger.warning("客资增量同步失败，将在下一轮重试: %s", safe_error)
            finally:
                db.close()
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=settings.KEZI_SYNC_INTERVAL_SECONDS,
                )
            except asyncio.TimeoutError:
                continue


kezi_lead_sync_manager = KeziLeadSyncManager()
