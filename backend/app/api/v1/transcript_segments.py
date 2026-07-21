"""话术分段 CRUD API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.transcript_segments import TranscriptSegment
from app.schemas import TranscriptSegmentCreate, TranscriptSegmentResponse, MessageResponse

router = APIRouter(prefix="/transcript-segments", tags=["话术分段"])


@router.get("/", response_model=list[TranscriptSegmentResponse])
def list_segments(
    session_id: int | None = Query(None),
    asr_status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """获取话术分段列表"""
    q = db.query(TranscriptSegment)
    if session_id:
        q = q.filter(TranscriptSegment.session_id == session_id)
    if asr_status:
        q = q.filter(TranscriptSegment.asr_status == asr_status)
    return q.order_by(TranscriptSegment.segment_start).offset(skip).limit(limit).all()


@router.get("/{seg_id}", response_model=TranscriptSegmentResponse)
def get_segment(seg_id: int, db: Session = Depends(get_db)):
    s = db.query(TranscriptSegment).get(seg_id)
    if not s:
        raise HTTPException(404, "话术分段不存在")
    return s


@router.post("/", response_model=TranscriptSegmentResponse)
def create_segment(data: TranscriptSegmentCreate, db: Session = Depends(get_db)):
    s = TranscriptSegment(**data.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.delete("/{seg_id}", response_model=MessageResponse)
def delete_segment(seg_id: int, db: Session = Depends(get_db)):
    s = db.query(TranscriptSegment).get(seg_id)
    if not s:
        raise HTTPException(404, "话术分段不存在")
    db.delete(s)
    db.commit()
    return {"message": "删除成功"}
