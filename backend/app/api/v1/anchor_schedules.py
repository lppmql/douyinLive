"""主播排班 API。"""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.schedule_service import build_schedule_dashboard


router = APIRouter(prefix="/anchor-schedules", tags=["主播排班"])


@router.get("/dashboard")
def get_schedule_dashboard(
    schedule_date: date | None = Query(None, description="排班日期，默认今天"),
    db: Session = Depends(get_db),
):
    """将固定排班与当天真实采集场次匹配并生成提醒。"""
    return build_schedule_dashboard(db, schedule_date or date.today())
