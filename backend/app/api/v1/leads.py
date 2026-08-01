"""留资查询、人工归属与 kezi 增量同步 API。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import is_valid_kezi_api_key, settings
from app.core.database import get_db
from app.core.logger import logger
from app.models.lead_sync_states import LeadSyncState
from app.models.leads import Lead
from app.models.lead_conversion_pairs import LeadConversionPair
from app.models.live_sessions import LiveSession
from app.schemas import LeadCreate, LeadResponse, MessageResponse
from app.schemas.leads import (
    LeadAttributionUpdate,
    LeadDetailResponse,
    LeadSyncResponse,
    LeadSyncStatusResponse,
)
from app.services.leads.kezi_sync import SOURCE_SYSTEM, rematch_pending_leads, sync_kezi_leads
from app.services.leads.lead_pairing import rebuild_lead_conversion_pairs

router = APIRouter(prefix="/leads", tags=["留资"])


def _refresh_session_lead_count(db: Session, session_id: int | None) -> None:
    """归属变化后重算真实有效数，旧场次和新场次都不能留下过期统计。"""
    if not session_id:
        return
    session = db.get(LiveSession, session_id)
    if session:
        session.leads_count = (
            db.query(LeadConversionPair.id)
            .filter(LeadConversionPair.session_id == session_id)
            .count()
        )


@router.get("/", response_model=list[LeadDetailResponse])
def list_leads(
    session_id: int | None = Query(None),
    is_valid: int | None = Query(None),
    attribution_status: str | None = Query(None, pattern="^(matched|pending)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """获取留资列表"""
    q = db.query(Lead)
    if session_id:
        q = q.filter(Lead.session_id == session_id)
    if is_valid is not None:
        q = q.filter(Lead.is_valid == is_valid)
    if attribution_status:
        q = q.filter(Lead.attribution_status == attribution_status)
    return q.order_by(Lead.create_time.desc()).offset(skip).limit(limit).all()


@router.get("/sync-status", response_model=LeadSyncStatusResponse)
def get_lead_sync_status(db: Session = Depends(get_db)):
    """返回游标和待归属数量，不把任何客户联系方式带到状态卡。"""
    state = db.query(LeadSyncState).filter(LeadSyncState.source_system == SOURCE_SYSTEM).first()
    configured = is_valid_kezi_api_key(settings.KEZI_API_KEY)
    return LeadSyncStatusResponse(
        configured=configured,
        status=state.status if state else "idle" if configured else "not_configured",
        last_external_id=int(state.last_external_id or 0) if state else 0,
        last_synced_at=state.last_synced_at if state else None,
        last_error=state.last_error if state else None,
        synced_count=int(state.synced_count or 0) if state else 0,
        duplicate_count=int(state.duplicate_count or 0) if state else 0,
        pending_count=(
            db.query(Lead.id)
            .filter(
                Lead.external_source == SOURCE_SYSTEM,
                Lead.attribution_status == "pending",
            )
            .count()
        ),
        interval_seconds=settings.KEZI_SYNC_INTERVAL_SECONDS,
    )


@router.post("/sync", response_model=LeadSyncResponse)
async def run_lead_sync(
    rematch: bool = Query(False, description="先重匹配待归属客资，再拉取新增"),
    db: Session = Depends(get_db),
):
    """立即拉取新增客资；传 ?rematch=true 会先把待归属客资重新匹配一遍。"""
    if not is_valid_kezi_api_key(settings.KEZI_API_KEY):
        raise HTTPException(
            409,
            "请在项目根目录 .env 配置至少 32 位、无空格的英文 KEZI_API_KEY",
        )
    try:
        rematch_result = None
        if rematch:
            rematch_result = rematch_pending_leads(db)
        sync_result = await sync_kezi_leads(db)
        if rematch_result:
            sync_result["rematch"] = rematch_result
        return sync_result
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("/{lead_id}", response_model=LeadDetailResponse)
def get_lead(lead_id: int, db: Session = Depends(get_db)):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "留资不存在")
    return lead


@router.post("/", response_model=LeadResponse)
def create_lead(data: LeadCreate, db: Session = Depends(get_db)):
    lead = Lead(**data.model_dump())
    db.add(lead)
    try:
        # 先把客资写进当前事务，再按真实有效客资重算场次统计。
        # 两步一起提交，避免列表里有客资但看板数量还是旧值。
        db.flush()
        rebuild_lead_conversion_pairs(db)
        _refresh_session_lead_count(db, lead.session_id)
        db.commit()
    except SQLAlchemyError as exc:
        # SQLAlchemy 完整异常可能把手机号等绑定参数写进 traceback。
        # 此处只记录异常类别，并用固定提示交给统一 HTTP 错误处理。
        db.rollback()
        logger.error("人工客资写入失败，数据库异常类型=%s", type(exc).__name__)
        raise HTTPException(500, "客资保存失败，请稍后重试") from exc
    db.refresh(lead)
    return lead


@router.patch("/{lead_id}/attribution", response_model=LeadDetailResponse)
def attribute_lead(
    lead_id: int,
    data: LeadAttributionUpdate,
    db: Session = Depends(get_db),
):
    """人工归属必须选择数据库里真实存在的场次。"""
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "留资不存在")
    session = db.get(LiveSession, data.session_id)
    if not session:
        raise HTTPException(404, "直播场次不存在")
    old_session_id = lead.session_id
    lead.session_id = session.id
    lead.attribution_status = "matched"
    if lead.remark == "未找到同主播且时间覆盖的真实直播场次，等待人工归属":
        lead.remark = None
    db.flush()
    rebuild_lead_conversion_pairs(db)
    _refresh_session_lead_count(db, old_session_id)
    _refresh_session_lead_count(db, session.id)
    db.commit()
    db.refresh(lead)
    return lead


@router.delete("/{lead_id}", response_model=MessageResponse)
def delete_lead(lead_id: int, db: Session = Depends(get_db)):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "留资不存在")
    old_session_id = lead.session_id
    db.delete(lead)
    db.flush()
    rebuild_lead_conversion_pairs(db)
    _refresh_session_lead_count(db, old_session_id)
    db.commit()
    return {"message": "删除成功"}
