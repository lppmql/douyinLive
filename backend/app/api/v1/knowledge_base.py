"""知识库 CRUD API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.knowledge_base import KnowledgeBase
from app.models.knowledge_time_slices import KnowledgeTimeSlice
from app.models.live_sessions import LiveSession
from app.core.config import settings
from app.schemas import KnowledgeBaseCreate, KnowledgeBaseResponse
from app.schemas.knowledge import (
    KnowledgePageResponse,
    KnowledgeTimeSliceStatusResponse,
    KnowledgeTimeSliceSearchResponse,
    KnowledgeTimeSliceSyncResponse,
    KnowledgeDeleteResponse,
)
from app.services.ai.time_slice_service import search_time_slices, sync_session_time_slices

router = APIRouter(prefix="/knowledge-base", tags=["知识库"])


def _serialize_time_slice(row: KnowledgeTimeSlice) -> dict:
    return {
        "id": row.id,
        "session_id": row.session_id,
        "anchor_name": row.anchor_name,
        "session_title": row.session_title,
        "slice_start_seconds": row.slice_start_seconds,
        "slice_end_seconds": row.slice_end_seconds,
        "slice_start_time": row.slice_start_time,
        "slice_end_time": row.slice_end_time,
        "transcript_text": row.transcript_text,
        "comments_text": row.comments_text,
        "comment_count": row.comment_count,
        "high_intent_comment_count": row.high_intent_comment_count,
        "unmapped_comment_count": row.unmapped_comment_count,
        "metric_point_count": row.metric_point_count,
        "avg_online_count": float(row.avg_online_count or 0),
        "peak_online_count": row.peak_online_count,
        "updated_at": row.updated_at,
    }


@router.get("/", response_model=list[KnowledgeBaseResponse])
def list_knowledge(
    category: str | None = Query(None),
    source_type: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """获取知识库列表"""
    q = db.query(KnowledgeBase)
    if category:
        q = q.filter(KnowledgeBase.category == category)
    if source_type:
        q = q.filter(KnowledgeBase.source_type == source_type)
    return q.order_by(KnowledgeBase.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/page", response_model=KnowledgePageResponse)
def page_knowledge(
    current: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    keyword: str | None = Query(None, max_length=200),
    category: str | None = Query(None),
    source_type: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """按 SoybeanAdmin 分页结构返回整场知识。"""
    query = db.query(KnowledgeBase)
    if keyword and keyword.strip():
        pattern = f"%{keyword.strip()}%"
        query = query.filter(or_(KnowledgeBase.title.like(pattern), KnowledgeBase.content.like(pattern)))
    if category:
        query = query.filter(KnowledgeBase.category == category)
    if source_type:
        query = query.filter(KnowledgeBase.source_type == source_type)

    total = query.count()
    rows = query.order_by(KnowledgeBase.created_at.desc(), KnowledgeBase.id.desc()).offset((current - 1) * size).limit(size).all()
    return {"records": rows, "total": total, "current": current, "size": size}


@router.get("/time-slices/status", response_model=KnowledgeTimeSliceStatusResponse)
def time_slice_status(db: Session = Depends(get_db)):
    """返回真实知识时间片覆盖情况。"""
    session_count = db.query(func.count(func.distinct(KnowledgeTimeSlice.session_id))).scalar() or 0
    return {
        "slice_count": db.query(func.count(KnowledgeTimeSlice.id)).scalar() or 0,
        "session_count": session_count,
        "transcript_slice_count": db.query(func.count(KnowledgeTimeSlice.id)).filter(
            KnowledgeTimeSlice.transcript_text.is_not(None),
        ).scalar() or 0,
        "comment_slice_count": db.query(func.count(KnowledgeTimeSlice.id)).filter(
            KnowledgeTimeSlice.comment_count > 0,
        ).scalar() or 0,
        "metric_slice_count": db.query(func.count(KnowledgeTimeSlice.id)).filter(
            KnowledgeTimeSlice.metric_point_count > 0,
        ).scalar() or 0,
        "high_intent_slice_count": db.query(func.count(KnowledgeTimeSlice.id)).filter(
            KnowledgeTimeSlice.high_intent_comment_count > 0,
        ).scalar() or 0,
        "unmapped_comment_count": db.query(func.sum(KnowledgeTimeSlice.unmapped_comment_count)).scalar() or 0,
        "knowledge_item_count": db.query(func.count(KnowledgeBase.id)).scalar() or 0,
        "latest_updated_at": db.query(func.max(KnowledgeTimeSlice.updated_at)).scalar(),
        "slice_seconds": settings.KNOWLEDGE_SLICE_SECONDS,
        "parser_version": "time-slice-v1",
    }


@router.get("/time-slices/search", response_model=KnowledgeTimeSliceSearchResponse)
def search_slices(
    query: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """搜索话术、评论和分钟指标已绑定的时间片。"""
    return search_time_slices(db, question=query, limit=limit)


@router.post("/time-slices/sync/{session_id}", response_model=KnowledgeTimeSliceSyncResponse)
def sync_time_slices(session_id: int, db: Session = Depends(get_db)):
    """幂等同步单场真实数据的知识时间片。"""
    if not db.get(LiveSession, session_id):
        raise HTTPException(404, "直播场次不存在")
    result = sync_session_time_slices(db, session_id)
    return {"status": "ok", "session_id": session_id, **result}


@router.get("/time-slices", response_model=list[dict])
def list_time_slices(
    session_id: int | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(KnowledgeTimeSlice)
    if session_id is not None:
        query = query.filter(KnowledgeTimeSlice.session_id == session_id)
    rows = query.order_by(
        KnowledgeTimeSlice.slice_start_time.desc(),
        KnowledgeTimeSlice.session_id.desc(),
        KnowledgeTimeSlice.slice_index,
    ).offset(skip).limit(limit).all()
    return [_serialize_time_slice(row) for row in rows]


@router.get("/time-slices/page", response_model=KnowledgePageResponse)
def page_time_slices(
    current: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    keyword: str | None = Query(None, max_length=200),
    anchor_name: str | None = Query(None, max_length=100),
    evidence_type: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """分页筛选真实知识时间片。"""
    query = db.query(KnowledgeTimeSlice)
    if keyword and keyword.strip():
        pattern = f"%{keyword.strip()}%"
        query = query.filter(or_(
            KnowledgeTimeSlice.anchor_name.like(pattern),
            KnowledgeTimeSlice.session_title.like(pattern),
            KnowledgeTimeSlice.transcript_text.like(pattern),
            KnowledgeTimeSlice.comments_text.like(pattern),
            KnowledgeTimeSlice.search_text.like(pattern),
        ))
    if anchor_name:
        query = query.filter(KnowledgeTimeSlice.anchor_name == anchor_name)
    if evidence_type == "transcript":
        query = query.filter(KnowledgeTimeSlice.transcript_text.is_not(None), KnowledgeTimeSlice.transcript_text != "")
    elif evidence_type == "comments":
        query = query.filter(KnowledgeTimeSlice.comment_count > 0)
    elif evidence_type == "metrics":
        query = query.filter(KnowledgeTimeSlice.metric_point_count > 0)
    elif evidence_type == "high_intent":
        query = query.filter(KnowledgeTimeSlice.high_intent_comment_count > 0)

    total = query.count()
    rows = query.order_by(
        KnowledgeTimeSlice.slice_start_time.desc(),
        KnowledgeTimeSlice.session_id.desc(),
        KnowledgeTimeSlice.slice_index,
    ).offset((current - 1) * size).limit(size).all()
    return {
        "records": [_serialize_time_slice(row) for row in rows],
        "total": total,
        "current": current,
        "size": size,
    }


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
def get_knowledge(kb_id: int, db: Session = Depends(get_db)):
    k = db.get(KnowledgeBase, kb_id)
    if not k:
        raise HTTPException(404, "知识条目不存在")
    return k


@router.post("/", response_model=KnowledgeBaseResponse)
def create_knowledge(data: KnowledgeBaseCreate, db: Session = Depends(get_db)):
    k = KnowledgeBase(**data.model_dump())
    db.add(k)
    db.commit()
    db.refresh(k)
    return k


@router.delete("/{kb_id}", response_model=KnowledgeDeleteResponse)
def delete_knowledge(kb_id: int, db: Session = Depends(get_db)):
    k = db.get(KnowledgeBase, kb_id)
    if not k:
        raise HTTPException(404, "知识条目不存在")
    db.delete(k)
    db.commit()
    return {"message": "删除成功"}
