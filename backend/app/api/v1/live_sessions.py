"""直播场次 CRUD API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.live_sessions import LiveSession
from app.models.live_rooms import LiveRoom
from app.models.live_metrics import LiveMetric
from app.models.comments import Comment
from app.models.stream_sources import StreamSource
from app.schemas import (
    LiveMetricDetailResponse,
    LiveSessionCreate,
    LiveSessionDetailResponse,
    LiveSessionResponse,
    LiveSessionUpdate,
)

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
    session = db.query(LiveSession).get(session_id)
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

    return LiveSessionDetailResponse(
        session=LiveSessionResponse(**_attach_room_profile(session)),
        metrics=[LiveMetricDetailResponse.model_validate(item, from_attributes=True) for item in metrics],
        comments=comments,
        stream_url=latest_stream or session.stream_url,
        stream_source_count=len(stream_sources),
    )


@router.get("/{session_id}", response_model=LiveSessionResponse)
def get_session(session_id: int, db: Session = Depends(get_db)):
    """获取单个直播场次"""
    s = db.query(LiveSession).get(session_id)
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
    s = db.query(LiveSession).get(session_id)
    if not s:
        raise HTTPException(404, "直播场次不存在")
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(s, key, val)
    db.commit()
    db.refresh(s)
    return s


@router.delete("/{session_id}")
def delete_session(session_id: int, db: Session = Depends(get_db)):
    """删除直播场次"""
    s = db.query(LiveSession).get(session_id)
    if not s:
        raise HTTPException(404, "直播场次不存在")
    db.delete(s)
    db.commit()
    return {"message": "删除成功"}
