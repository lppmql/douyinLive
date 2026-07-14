"""直播场次 CRUD API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.live_sessions import LiveSession
from app.models.live_rooms import LiveRoom
from app.models.live_metrics import LiveMetric
from app.models.comments import Comment
from app.models.stream_sources import StreamSource
from app.models.live_audience_profiles import LiveAudienceProfile
from app.models.asr_tasks import AsrTask
from app.models.scraper_tasks import ScraperTask
from app.models.scraper_logs import ScraperLog
from app.models.transcript_segments import TranscriptSegment
from app.models.transcript_full_texts import TranscriptFullText
from app.models.analysis_reports import AnalysisReport
from app.models.high_intent_users import HighIntentUser
from app.models.knowledge_base import KnowledgeBase
from app.models.leads import Lead
from app.schemas import (
    LiveMetricDetailResponse,
    LiveSessionCreate,
    LiveSessionDetailResponse,
    LiveSessionResponse,
    LiveSessionUpdate,
)


class BatchDeleteRequest(BaseModel):
    ids: list[int]

router = APIRouter(prefix="/live-sessions", tags=["直播场次"])


def _attach_room_profile(session: LiveSession) -> dict:
    """将 LiveRoom 上的主播资料注入到场次返回数据中。"""
    data = {c.name: getattr(session, c.name) for c in session.__table__.columns}
    # 企业主账号下一个入口对应多个主播，不能把未映射场次伪装成入口账号主播。
    data["anchor_name"] = session.anchor_name
    data["anchor_nickname"] = session.anchor_nickname
    data["anchor_avatar_url"] = session.anchor_avatar_url
    data["douyin_id"] = session.douyin_id
    data["douyin_uid"] = session.douyin_uid
    return data


@router.get("/page")
def page_sessions(
    current: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=2000),
    anchor_name: str | None = Query(None),
    live_status: str | None = Query(None),
    detail_status: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """按 SoybeanAdmin 分页结构返回全部直播场次。"""
    query = db.query(LiveSession)
    if anchor_name:
        query = query.filter(LiveSession.anchor_name.like(f"%{anchor_name.strip()}%"))
    if live_status:
        query = query.filter(LiveSession.live_status == live_status)
    if detail_status:
        query = query.filter(LiveSession.detail_collection_status == detail_status)

    total = query.count()
    sessions = (
        query.order_by(LiveSession.live_start_time.desc(), LiveSession.id.desc())
        .offset((current - 1) * size)
        .limit(size)
        .all()
    )
    return {
        "records": [LiveSessionResponse(**_attach_room_profile(session)) for session in sessions],
        "total": total,
        "current": current,
        "size": size,
    }


@router.get("/", response_model=list[LiveSessionResponse])
def list_sessions(
    room_id: int | None = Query(None, description="按直播间筛选"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """获取直播场次列表"""
    q = db.query(LiveSession)
    if room_id:
        q = q.filter(LiveSession.room_id == room_id)
    sessions = q.order_by(LiveSession.live_start_time.desc()).offset(skip).limit(limit).all()
    return [LiveSessionResponse(**_attach_room_profile(s)) for s in sessions]


@router.get("/{session_id}/details", response_model=LiveSessionDetailResponse)
def get_session_details(
    session_id: int,
    comment_limit: int = Query(300, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """获取单场直播的大屏趋势、已采集评论和可用流地址。"""
    session = db.get(LiveSession, session_id)
    if not session:
        raise HTTPException(404, "直播场次不存在")

    metrics = (
        db.query(LiveMetric)
        .filter(LiveMetric.session_id == session_id)
        .order_by(LiveMetric.metric_time.asc())
        .all()
    )
    comments = (
        db.query(Comment)
        .filter(Comment.session_id == session_id)
        .order_by(Comment.comment_time.desc(), Comment.id.desc())
        .limit(comment_limit)
        .all()
    )
    stream_sources = (
        db.query(StreamSource)
        .filter(StreamSource.session_id == session_id)
        .order_by(StreamSource.fetched_at.desc(), StreamSource.id.desc())
        .all()
    )
    latest_stream = next((item.m3u8_url for item in stream_sources if item.status == "active"), None)
    profiles = (
        db.query(LiveAudienceProfile)
        .filter(LiveAudienceProfile.session_id == session_id)
        .order_by(LiveAudienceProfile.dimension_type, LiveAudienceProfile.ratio.desc())
        .all()
    )

    return LiveSessionDetailResponse(
        session=LiveSessionResponse(**_attach_room_profile(session)),
        metrics=[LiveMetricDetailResponse.model_validate(item, from_attributes=True) for item in metrics],
        comments=comments,
        profiles=profiles,
        stream_url=latest_stream or session.stream_url,
        stream_source_count=len(stream_sources),
    )


@router.get("/{session_id}", response_model=LiveSessionResponse)
def get_session(session_id: int, db: Session = Depends(get_db)):
    """获取单个直播场次"""
    s = db.get(LiveSession, session_id)
    if not s:
        raise HTTPException(404, "直播场次不存在")
    return LiveSessionResponse(**_attach_room_profile(s))


@router.post("/", response_model=LiveSessionResponse)
def create_session(data: LiveSessionCreate, db: Session = Depends(get_db)):
    """创建直播场次"""
    s = LiveSession(**data.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.put("/{session_id}", response_model=LiveSessionResponse)
def update_session(session_id: int, data: LiveSessionUpdate, db: Session = Depends(get_db)):
    """更新直播场次"""
    s = db.get(LiveSession, session_id)
    if not s:
        raise HTTPException(404, "直播场次不存在")
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(s, key, val)
    db.commit()
    db.refresh(s)
    return s


@router.post("/batch-delete")
def batch_delete_sessions(body: BatchDeleteRequest, db: Session = Depends(get_db)):
    """批量删除直播场次（级联删除关联的指标、评论、流地址、画像等数据）"""
    if not body.ids:
        raise HTTPException(400, "请提供要删除的场次 ID 列表")
    if len(body.ids) > 2000:
        raise HTTPException(400, "单次最多删除 2000 个场次")

    sessions = db.query(LiveSession).filter(LiveSession.id.in_(body.ids)).all()
    found_ids = {s.id for s in sessions}
    not_found = set(body.ids) - found_ids
    if not sessions:
        raise HTTPException(404, "未找到要删除的场次")

    # 级联删除关联数据（按外键约束顺序，先删子表再删主表）
    for sid in found_ids:
        db.query(AnalysisReport).filter(AnalysisReport.session_id == sid).delete()
        db.query(HighIntentUser).filter(HighIntentUser.session_id == sid).delete()
        db.query(KnowledgeBase).filter(KnowledgeBase.session_id == sid).delete()
        db.query(Lead).filter(Lead.session_id == sid).delete()
        db.query(TranscriptSegment).filter(TranscriptSegment.session_id == sid).delete()
        db.query(TranscriptFullText).filter(TranscriptFullText.session_id == sid).delete()
        db.query(AsrTask).filter(AsrTask.session_id == sid).delete()
        # 先删 scraper_logs（外键 fk_scraper_logs_task 引用了 scraper_tasks.id）
        task_ids = db.query(ScraperTask.id).filter(ScraperTask.session_id == sid).all()
        task_id_list = [t[0] for t in task_ids]
        if task_id_list:
            db.query(ScraperLog).filter(ScraperLog.task_id.in_(task_id_list)).delete(synchronize_session=False)
        db.query(ScraperTask).filter(ScraperTask.session_id == sid).delete()
        db.query(LiveMetric).filter(LiveMetric.session_id == sid).delete()
        db.query(Comment).filter(Comment.session_id == sid).delete()
        db.query(StreamSource).filter(StreamSource.session_id == sid).delete()
        db.query(LiveAudienceProfile).filter(LiveAudienceProfile.session_id == sid).delete()

    # 删除场次
    for s in sessions:
        db.delete(s)
    db.commit()

    return {
        "message": f"已删除 {len(sessions)} 个场次",
        "deleted_count": len(sessions),
        "not_found_ids": list(not_found) if not_found else None,
    }


@router.delete("/{session_id}")
def delete_session(session_id: int, db: Session = Depends(get_db)):
    """删除直播场次"""
    s = db.get(LiveSession, session_id)
    if not s:
        raise HTTPException(404, "直播场次不存在")
    db.delete(s)
    db.commit()
    return {"message": "删除成功"}
