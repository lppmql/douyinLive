"""从 kezi.lpp6.com 增量同步真实客资。

"增量同步"大白话：服务只从上次成功保存的编号继续往后拉，不会每分钟
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
from app.models.lead_conversion_pairs import LeadConversionPair
from app.services.leads.lead_pairing import rebuild_lead_conversion_pairs


SOURCE_SYSTEM = "kezi"
_SYNC_LOCK = asyncio.Lock()
_SHANGHAI = ZoneInfo("Asia/Shanghai")


class KeziSyncError(RuntimeError):
    """可以安全展示给管理员的同步错误，不包含响应正文或数据库参数。"""


class KeziLeadItem(BaseModel):
    """客资服务返回的单条真实记录。"""

    model_config = ConfigDict(populate_by_name=True)

    source_id: int = Field(alias="sourceId", gt=0)
    phone: str = Field(default="", max_length=100)
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


def _anchor_name_filter(anchor: str):
    """主播名模糊匹配条件：精确 + 包含。

    解决 kezi 短名 vs 直播间完整标题的对应问题：
    - 大全 包含在 大全谈开店天准 里 -> contains
    """
    return or_(
        LiveSession.anchor_name == anchor,
        LiveSession.anchor_nickname == anchor,
        LiveSession.anchor_name.contains(anchor),
        LiveSession.anchor_nickname.contains(anchor),
    )


def _query_candidates(db: Session, anchor_name: str) -> list[LiveSession]:
    """分层查询候选场次：先精确+包含，没结果再用首字兜底。

    分层是为了防止首字匹配太宽（如"主"匹配到"主播甲"和"主播乙"）。
    """
    # 第 1 层：精确 + 包含匹配
    candidates = (
        db.query(LiveSession)
        .filter(
            _anchor_name_filter(anchor_name),
            LiveSession.live_start_time.isnot(None),
        )
        .order_by(LiveSession.live_start_time.desc())
        .all()
    )
    if candidates:
        return candidates

    # 第 2 层：首字匹配兜底（第 1 层精确+包含没命中，只需首字条件）
    if len(anchor_name) >= 1:
        candidates = (
            db.query(LiveSession)
            .filter(
                or_(
                    LiveSession.anchor_name.startswith(anchor_name[0]),
                    LiveSession.anchor_nickname.startswith(anchor_name[0]),
                ),
                LiveSession.live_start_time.isnot(None),
            )
            .order_by(LiveSession.live_start_time.desc())
            .all()
        )
    return candidates


def _get_session_end_time(session: LiveSession) -> datetime | None:
    """计算直播场次的结束时间（优先用记录值，其次用时长推算）。"""
    if session.live_end_time:
        return session.live_end_time
    if int(session.live_duration_seconds or 0) > 0:
        return session.live_start_time + timedelta(seconds=int(session.live_duration_seconds))
    if session.live_status == "live":
        return datetime.now(_SHANGHAI).replace(tzinfo=None) + timedelta(minutes=5)
    return None


def _pick_closest_session(sessions: list[LiveSession], lead_time: datetime) -> LiveSession | None:
    """同天多场次时，找离客资时间最近的一场。

    优先级（从高到低）：
    1. 客资落在直播时段内（start <= lead <= end）→ 最佳匹配，选最接近结束时间的
    2. 刚下播的（end_time < lead_time 且时间差最小）
    3. 马上要播的（start_time > lead_time 且时间差最小）
    """
    # 最高优先：客资落在直播时段内（不含缓冲），越接近结束越可能是直播中留资
    during_live: list[tuple[LiveSession, timedelta]] = []
    for s in sessions:
        end = _get_session_end_time(s)
        if end and s.live_start_time and s.live_start_time <= lead_time <= end:
            during_live.append((s, end - lead_time))
    if during_live:
        during_live.sort(key=lambda x: x[1])
        return during_live[0][0]

    # 其次：lead_time 之前结束的场次中，结束时间最晚的那个
    ended_before: list[tuple[LiveSession, timedelta]] = []
    for s in sessions:
        end = _get_session_end_time(s)
        if end and end < lead_time:
            ended_before.append((s, lead_time - end))
    if ended_before:
        ended_before.sort(key=lambda x: x[1])
        return ended_before[0][0]

    # 再次：lead_time 之后开始的场次中，开始时间最早的那个
    starts_after: list[tuple[LiveSession, timedelta]] = []
    for s in sessions:
        if s.live_start_time and s.live_start_time > lead_time:
            starts_after.append((s, s.live_start_time - lead_time))
    if starts_after:
        starts_after.sort(key=lambda x: x[1])
        return starts_after[0][0]

    return None


def match_live_session(db: Session, item: KeziLeadItem) -> tuple[LiveSession | None, str | None]:
    """四级匹配客资到直播场次。返回 (场次, 匹配方式)。

    匹配方式（用于设置备注）：
    - "time_window": 时间窗精确匹配，无需备注
    - "same_day": 同天仅 1 场，兜底归属
    - "gap": 同天多场次间隙，就近匹配，备注"下播后留资"
    - "no_session_today": 当天无直播，按主播就近匹配，备注"当天无直播记录 / 换号播的"
    - None: 无法匹配，进入"待归属"
    """
    if not item.anchor or not item.anchor.strip():
        return None, None

    anchor_name = item.anchor.strip()

    # ── 分层查询候选场次（精确+包含 -> 首字兜底） ──────────
    candidates = _query_candidates(db, anchor_name)

    if not candidates:
        return None, None

    # ── 第 1 级：时间窗匹配（含缓冲） ────────────────────────
    BUFFER_BEFORE = timedelta(minutes=30)   # 开播前 30 分钟
    BUFFER_AFTER = timedelta(minutes=60)    # 下播后 60 分钟

    time_matched: list[LiveSession] = []
    for session in candidates:
        end_time = _get_session_end_time(session)
        if end_time is None:
            continue
        window_start = session.live_start_time - BUFFER_BEFORE
        window_end = end_time + BUFFER_AFTER
        if window_start <= item.created_at <= window_end:
            time_matched.append(session)

    # 恰好 1 个时间窗匹配 -> 精确归属
    if len(time_matched) == 1:
        return time_matched[0], "time_window"

    # 多个时间窗同时覆盖 -> 用 _pick_closest_session 去重
    # 优先选客资落在直播时段内的，其次选最近场次
    if len(time_matched) > 1:
        closest = _pick_closest_session(time_matched, item.created_at)
        if closest:
            return closest, "time_window"
        return None, None

    # ── 第 2 级：同一天兜底 ──────────────────────────────────
    if item.created_at is None:
        return None, None

    lead_date = item.created_at.date()
    same_day = [s for s in candidates if s.live_start_time.date() == lead_date]

    # 同一天恰好 1 个场次 -> 兜底归属
    if len(same_day) == 1:
        return same_day[0], "same_day"

    # ── 第 3 级：同天多场次，就近匹配 ────────────────────────
    if len(same_day) > 1:
        closest = _pick_closest_session(same_day, item.created_at)
        if closest:
            return closest, "gap"

    # ── 第 4 级：当天没直播，不限日期按主播就近匹配 ──────────
    # 第 3 级都没匹配上（同天 0 场或 _pick_closest_session 返回 None），
    # 说明主播当天没播或当天场次信息不全。此时放宽到所有候选场次，
    # 按时间就近匹配，备注"当天无直播记录 / 换号播的"。
    if len(same_day) == 0 and candidates:
        closest = _pick_closest_session(candidates, item.created_at)
        if closest:
            return closest, "no_session_today"

    return None, None


def _save_item(db: Session, item: KeziLeadItem) -> tuple[bool, int | None]:
    """幂等保存一条客资，返回"是否新增"和匹配到的场次编号。"""
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

    session, match_reason = match_live_session(db, item)

    # 根据匹配方式设置备注
    if session:
        if match_reason == "gap":
            remark = "下播后留资（自动匹配到最近场次）"
        elif match_reason == "no_session_today":
            remark = "当天无直播记录 / 换号播的"
        else:
            remark = None
    else:
        # 无法匹配：检查是"换号播"（从未有此主播的直播记录）还是"当天没播"
        anchor = (item.anchor or "").strip()
        any_candidates = _query_candidates(db, anchor)
        if any_candidates:
            remark = "未找到同主播且时间覆盖的真实直播场次，等待人工归属"
        else:
            remark = "换号播的"

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
        remark=remark,
    )
    db.add(lead)
    return True, session.id if session else None


def _refresh_session_lead_counts(db: Session, session_ids: set[int]) -> None:
    """按已完成一分钟配对的确认客资更新场次数量。"""
    # 新客资刚加入 Session 但尚未提交，先 flush 才能让下面的 COUNT 看见它。
    db.flush()
    for session_id in session_ids:
        session = db.get(LiveSession, session_id)
        if session is None:
            continue
        session.leads_count = (
            db.query(LeadConversionPair.id)
            .filter(
                LeadConversionPair.session_id == session_id,
            )
            .count()
        )


def rematch_pending_leads(db: Session) -> dict:
    """把已有的「待归属」客资重新匹配一遍。

    什么时候用：匹配逻辑更新后（比如名字模糊匹配上线），
    把之前因为匹配不上而进入 pending 的客资拉回来重新跑一次。
    """
    pending_leads = (
        db.query(Lead)
        .filter(
            Lead.external_source == SOURCE_SYSTEM,
            Lead.attribution_status == "pending",
        )
        .all()
    )

    if not pending_leads:
        return {"matched_count": 0, "still_pending": 0}

    matched_count = 0
    still_pending = 0
    affected_sessions: set[int] = set()

    for lead in pending_leads:
        # 用客资数据构造匹配输入（sourceId 取 safe 值，匹配逻辑不用它）
        item = KeziLeadItem(
            sourceId=max(lead.external_id or 1, 1),
            phone=lead.lead_phone or "",
            douyinId=lead.douyin_id or "",
            anchor=lead.anchor_name or "",
            createdAt=lead.create_time or datetime.min,
        )
        session, match_reason = match_live_session(db, item)
        if session:
            lead.session_id = session.id
            lead.attribution_status = "matched"
            if match_reason == "gap":
                lead.remark = "下播后留资（自动匹配到最近场次）"
            elif match_reason == "no_session_today":
                lead.remark = "当天无直播记录 / 换号播的"
            else:
                lead.remark = None
            matched_count += 1
            affected_sessions.add(session.id)
        else:
            # 更新备注：区分"换号播"和"当天没播"
            anchor = (lead.anchor_name or "").strip()
            any_candidates = _query_candidates(db, anchor)
            lead.remark = "未找到同主播且时间覆盖的真实直播场次，等待人工归属" if any_candidates else "换号播的"
            still_pending += 1

    rebuild_lead_conversion_pairs(db)
    _refresh_session_lead_counts(db, affected_sessions)
    db.commit()

    logger.info(
        "客资重匹配完成：%s 条已归属，%s 条仍待归属",
        matched_count,
        still_pending,
    )
    return {
        "matched_count": matched_count,
        "still_pending": still_pending,
    }


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
        pair_result = {"pair_count": 0}
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

            # 一次同步批次只全量重建一次，避免每页重复扫描全部历史数据。
            pair_result = rebuild_lead_conversion_pairs(db)
            db.commit()

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
                # 前端展示系统当前仍需人工处理的总数，而不是"本轮新增待归属数"。
                "pending_count": int(state.pending_count or 0),
                "last_external_id": int(state.last_external_id or 0),
                "page_count": pages,
                "paired_count": pair_result["pair_count"] if pages else 0,
            }
        except Exception as exc:
            db.rollback()
            # 前面页已经按页提交时，即使后续请求失败也要把已入库原始记录配对完。
            if pages:
                try:
                    rebuild_lead_conversion_pairs(db)
                    db.commit()
                except Exception:
                    db.rollback()
                    logger.exception("客资同步失败后重建确认配对失败")
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
