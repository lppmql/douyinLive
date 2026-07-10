"""Phase 3: 采集状态 & 扫码登录 API"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.scraper_accounts import ScraperAccount
from app.models.scraper_tasks import ScraperTask
from app.models.scraper_logs import ScraperLog
from app.schemas.scraper import (
    ScraperAccountResponse,
    ScraperAccountCreate,
    ScraperAccountUpdate,
    ScraperTaskResponse,
    ScraperLogResponse,
    CollectorStatusResponse,
    LoginStartResponse,
    LoginStatusResponse,
    CollectAllResponse,
)
from app.services.collector.browser import browser_manager
from app.services.collector.manual_collect import collect_all

router = APIRouter(prefix="/collector", tags=["数据采集"])


# ===== 采集器状态 =====
@router.get("/status", response_model=CollectorStatusResponse)
def get_collector_status(db: Session = Depends(get_db)):
    """获取采集器整体状态"""
    active_count = db.query(ScraperTask).filter(ScraperTask.status == "running").count()
    default_account = db.query(ScraperAccount).order_by(ScraperAccount.last_login_at.desc()).first()
    return CollectorStatusResponse(
        connected=default_account is not None,
        active_task_count=active_count,
        default_account=ScraperAccountResponse.model_validate(default_account) if default_account else None,
    )


# ===== 账号管理 =====
@router.get("/accounts", response_model=list[ScraperAccountResponse])
def list_accounts(db: Session = Depends(get_db)):
    """获取所有采集账号"""
    return db.query(ScraperAccount).order_by(ScraperAccount.id.desc()).all()


@router.get("/accounts/{account_id}", response_model=ScraperAccountResponse)
def get_account(account_id: int, db: Session = Depends(get_db)):
    """获取单个账号详情"""
    account = db.query(ScraperAccount).get(account_id)
    if not account:
        raise HTTPException(404, "账号不存在")
    return account


@router.post("/accounts", response_model=ScraperAccountResponse)
def create_account(data: ScraperAccountCreate, db: Session = Depends(get_db)):
    """创建采集账号"""
    account = ScraperAccount(**data.model_dump())
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.put("/accounts/{account_id}", response_model=ScraperAccountResponse)
def update_account(account_id: int, data: ScraperAccountUpdate, db: Session = Depends(get_db)):
    """更新采集账号"""
    account = db.query(ScraperAccount).get(account_id)
    if not account:
        raise HTTPException(404, "账号不存在")
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(account, key, val)
    db.commit()
    db.refresh(account)
    return account


@router.delete("/accounts/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    """删除采集账号"""
    account = db.query(ScraperAccount).get(account_id)
    if not account:
        raise HTTPException(404, "账号不存在")
    db.delete(account)
    db.commit()
    return {"message": "删除成功"}


# ===== 扫码登录 =====
@router.post("/accounts/login", response_model=LoginStartResponse)
async def start_login(db: Session = Depends(get_db)):
    """启动扫码登录（后台打开有头浏览器）"""
    task = ScraperTask(task_type="login", status="running", started_at=datetime.utcnow())
    # 先 flush 获取 ID
    db.add(task)
    db.commit()
    db.refresh(task)

    # 在后台启动浏览器扫码
    await browser_manager.start_qr_login(task.id)

    return LoginStartResponse(task_id=task.id, message="请使用抖音扫描二维码")


@router.get("/login-tasks/{task_id}/qr")
async def get_login_qr(task_id: int):
    """获取登录二维码 base64"""
    qr = await browser_manager.get_login_qr(task_id)
    if qr is None:
        raise HTTPException(404, "登录任务不存在")
    return {"qr_code_base64": qr}


@router.get("/login-tasks/{task_id}/status", response_model=LoginStatusResponse)
async def get_login_status(task_id: int, db: Session = Depends(get_db)):
    """检查登录状态"""
    state = await browser_manager.get_login_status(task_id)

    if state["status"] == "not_found":
        task = db.query(ScraperTask).get(task_id)
        if not task:
            raise HTTPException(404, "登录任务不存在")
        return LoginStatusResponse(status=task.status, message="任务已结束")

    # 登录成功 → 查找已保存的账号记录（_qr_login_worker 已直接写入）
    if state["status"] == "success":
        account_name = f"采集账号_{task_id}"
        account = db.query(ScraperAccount).filter(
            ScraperAccount.account_name == account_name
        ).order_by(ScraperAccount.id.desc()).first()

        if account:
            return LoginStatusResponse(
                status="success",
                account=ScraperAccountResponse.model_validate(account),
                message="登录成功",
            )

    return LoginStatusResponse(
        status=state["status"],
        message=state.get("message", ""),
    )


@router.post("/accounts/{account_id}/re-login", response_model=LoginStartResponse)
async def re_login(account_id: int, db: Session = Depends(get_db)):
    """过期账号重新扫码登录"""
    account = db.query(ScraperAccount).get(account_id)
    if not account:
        raise HTTPException(404, "账号不存在")

    task = ScraperTask(task_type="login", status="running")
    db.add(task)
    db.commit()
    db.refresh(task)

    await browser_manager.start_qr_login(task.id, account.account_name or "unknown")

    return LoginStartResponse(task_id=task.id, message="请使用抖音扫描二维码")


# ===== 采集日志 =====
@router.get("/logs", response_model=list[ScraperLogResponse])
def list_logs(
    task_id: Optional[int] = Query(None),
    level: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
):
    """获取采集日志"""
    q = db.query(ScraperLog)
    if task_id:
        q = q.filter(ScraperLog.task_id == task_id)
    if level:
        q = q.filter(ScraperLog.level == level)
    return q.order_by(ScraperLog.id.desc()).limit(limit).all()


# ===== 采集任务 =====
@router.get("/tasks", response_model=list[ScraperTaskResponse])
def list_tasks(
    status: Optional[str] = Query(None),
    task_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """获取采集任务列表"""
    q = db.query(ScraperTask)
    if status:
        q = q.filter(ScraperTask.status == status)
    if task_type:
        q = q.filter(ScraperTask.task_type == task_type)
    return q.order_by(ScraperTask.id.desc()).limit(50).all()


# ===== 一键采集 =====
@router.post("/collect-all", response_model=CollectAllResponse)
async def manual_collect_all(db: Session = Depends(get_db)):
    """一键采集所有主播房间的大屏数据"""
    result = await collect_all(db)
    return result
