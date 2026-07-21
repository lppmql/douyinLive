"""AI 分析报告 CRUD API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.analysis_reports import AnalysisReport
from app.schemas import AnalysisReportCreate, AnalysisReportResponse, MessageResponse

router = APIRouter(prefix="/analysis-reports", tags=["AI 分析报告"])


@router.get("/", response_model=list[AnalysisReportResponse])
def list_reports(
    session_id: int | None = Query(None),
    report_type: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """获取分析报告列表"""
    q = db.query(AnalysisReport)
    if session_id:
        q = q.filter(AnalysisReport.session_id == session_id)
    if report_type:
        q = q.filter(AnalysisReport.report_type == report_type)
    return q.order_by(AnalysisReport.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/{report_id}", response_model=AnalysisReportResponse)
def get_report(report_id: int, db: Session = Depends(get_db)):
    r = db.query(AnalysisReport).get(report_id)
    if not r:
        raise HTTPException(404, "报告不存在")
    return r


@router.post("/", response_model=AnalysisReportResponse)
def create_report(data: AnalysisReportCreate, db: Session = Depends(get_db)):
    r = AnalysisReport(**data.model_dump())
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@router.delete("/{report_id}", response_model=MessageResponse)
def delete_report(report_id: int, db: Session = Depends(get_db)):
    r = db.query(AnalysisReport).get(report_id)
    if not r:
        raise HTTPException(404, "报告不存在")
    db.delete(r)
    db.commit()
    return {"message": "删除成功"}
