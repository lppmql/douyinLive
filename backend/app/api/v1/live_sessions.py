"""直播场次 CRUD API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.live_sessions import LiveSession
from app.schemas import LiveSessionCreate, LiveSessionUpdate, LiveSessionResponse

router = APIRouter(prefix="/live-sessions", tags=["直播场次"])


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
    return q.order_by(LiveSession.live_start_time.desc()).offset(skip).limit(limit).all()


@router.get("/{session_id}", response_model=LiveSessionResponse)
def get_session(session_id: int, db: Session = Depends(get_db)):
    """获取单个直播场次"""
    s = db.query(LiveSession).get(session_id)
    if not s:
        raise HTTPException(404, "直播场次不存在")
    return s


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
