"""留资 CRUD API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.leads import Lead
from app.schemas import LeadCreate, LeadResponse

router = APIRouter(prefix="/leads", tags=["留资"])


@router.get("/", response_model=list[LeadResponse])
def list_leads(
    session_id: int | None = Query(None),
    is_valid: int | None = Query(None),
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
    return q.order_by(Lead.create_time.desc()).offset(skip).limit(limit).all()


@router.get("/{lead_id}", response_model=LeadResponse)
def get_lead(lead_id: int, db: Session = Depends(get_db)):
    l = db.query(Lead).get(lead_id)
    if not l:
        raise HTTPException(404, "留资不存在")
    return l


@router.post("/", response_model=LeadResponse)
def create_lead(data: LeadCreate, db: Session = Depends(get_db)):
    l = Lead(**data.model_dump())
    db.add(l)
    db.commit()
    db.refresh(l)
    return l


@router.delete("/{lead_id}")
def delete_lead(lead_id: int, db: Session = Depends(get_db)):
    l = db.query(Lead).get(lead_id)
    if not l:
        raise HTTPException(404, "留资不存在")
    db.delete(l)
    db.commit()
    return {"message": "删除成功"}
