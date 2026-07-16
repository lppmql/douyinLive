"""主播排班 API。"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.schedule_service import build_schedule_dashboard, build_schedule_range_dashboard


router = APIRouter(prefix="/anchor-schedules", tags=["主播排班"])


@router.get("/dashboard")
def get_schedule_dashboard(
    schedule_date: date | None = Query(None, description="排班日期，默认今天"),
    start_date: date | None = Query(None, description="范围开始日期，和结束日期同时使用"),
    end_date: date | None = Query(None, description="范围结束日期，和开始日期同时使用"),
    db: Session = Depends(get_db),
):
    """将固定排班与单日或日期范围内的真实采集场次匹配并生成提醒。"""
    if start_date is not None or end_date is not None:
        selected_start = start_date or end_date or date.today()
        selected_end = end_date or start_date or selected_start
        try:
            return build_schedule_range_dashboard(db, selected_start, selected_end)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return build_schedule_dashboard(db, schedule_date or date.today())
