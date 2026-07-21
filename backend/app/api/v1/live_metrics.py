"""直播指标 CRUD API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.live_metrics import LiveMetric
from app.schemas import MessageResponse
from pydantic import BaseModel, ConfigDict
from datetime import datetime


class MetricCreate(BaseModel):
    session_id: int
    metric_time: datetime
    exposure_count: int = 0
    online_count: int = 0
    enter_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    follow_count: int = 0


class MetricResponse(MetricCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime

router = APIRouter(prefix="/live-metrics", tags=["直播指标"])


@router.get("/", response_model=list[MetricResponse])
def list_metrics(
    session_id: int | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    """获取指标列表（按时间升序）"""
    q = db.query(LiveMetric)
    if session_id:
        q = q.filter(LiveMetric.session_id == session_id)
    return q.order_by(LiveMetric.metric_time).offset(skip).limit(limit).all()


@router.post("/", response_model=MetricResponse)
def create_metric(data: MetricCreate, db: Session = Depends(get_db)):
    m = LiveMetric(**data.model_dump())
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@router.delete("/{metric_id}", response_model=MessageResponse)
def delete_metric(metric_id: int, db: Session = Depends(get_db)):
    m = db.query(LiveMetric).get(metric_id)
    if not m:
        raise HTTPException(404, "指标不存在")
    db.delete(m)
    db.commit()
    return {"message": "删除成功"}
