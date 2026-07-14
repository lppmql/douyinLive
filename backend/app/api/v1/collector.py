"""Phase 3: 采集状态 & 扫码登录 API"""
import asyncio
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
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
    AccountHealthResponse,
    AsrControlResponse,
    CollectAllResponse,
)
from app.services.collector.browser import browser_manager
from app.services.collector.browser import STORAGE_DIR
from app.services.collector.manual_collect import collect_all
from app.services.collector.scheduler import scheduler_manager
from app.services.asr.control import get_asr_runtime_status, start_asr_runtime, stop_asr_runtime
from app.models.asr_tasks import AsrTask

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
async def delete_account(account_id: int, db: Session = Depends(get_db)):
    """删除采集账号，并保留历史采集任务与业务数据。"""
    account = db.query(ScraperAccount).get(account_id)
    if not account:
        raise HTTPException(404, "账号不存在")

    running_task_count = db.query(ScraperTask).filter(
        ScraperTask.account_id == account_id,
        ScraperTask.status == "running",
    ).count()
    if running_task_count:
        raise HTTPException(409, "该账号仍有采集任务在运行，请等待任务结束后再删除")

    # 任务记录用于审计，删除账号时仅解除关联，避免外键约束导致 500。
    task_count = db.query(ScraperTask).filter(
        ScraperTask.account_id == account_id,
    ).update({ScraperTask.account_id: None}, synchronize_session=False)
    storage_state_path = account.storage_state_path
    db.delete(account)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "删除账号失败，请稍后重试")

    # 只删除系统存储目录内的状态文件，避免误删用户填写的其他本地文件。
    if browser_manager._logged_in_account_id == account_id:
        await browser_manager.close()
    if storage_state_path:
        try:
            state_path = Path(storage_state_path).resolve()
            if state_path.parent == STORAGE_DIR.resolve() and state_path.is_file():
                state_path.unlink()
        except OSError:
            # 数据库账号已删除；遗留状态文件不会影响后续账号登录。
            pass

    return {"message": "删除成功", "detached_task_count": task_count}


@router.post("/accounts/{account_id}/health", response_model=AccountHealthResponse)
async def check_account_health(account_id: int, db: Session = Depends(get_db)):
    """静默验证账号 Cookie 是否仍然有效，不执行数据采集。"""
    account = db.query(ScraperAccount).get(account_id)
    if not account:
        raise HTTPException(404, "账号不存在")
    if scheduler_manager.running:
        raise HTTPException(409, "直播监控运行中，请先停止监控再检查账号")
    if db.query(ScraperTask).filter(ScraperTask.status == "running").count():
        raise HTTPException(409, "当前有采集任务运行，请等待任务结束后再检查账号")

    valid, message = await browser_manager.check_account_health(account)
    account.login_status = "logged_in" if valid else "expired"
    db.commit()
    return AccountHealthResponse(
        account_id=account.id,
        valid=valid,
        login_status=account.login_status,
        checked_at=datetime.utcnow(),
        message=message,
    )


def _asr_control_response(db: Session, runtime: dict, message: str = "") -> AsrControlResponse:
    queued_count = db.query(AsrTask).filter(AsrTask.status == "queued").count()
    processing_count = db.query(AsrTask).filter(AsrTask.status == "processing").count()
    return AsrControlResponse(
        enabled=runtime["enabled"],
        engine_running=runtime["engine_running"],
        worker_running=runtime["worker_running"],
        queued_count=queued_count,
        processing_count=processing_count,
        message=message,
    )


@router.get("/asr-control", response_model=AsrControlResponse)
async def get_asr_control(db: Session = Depends(get_db)):
    """获取本地 ASR 模型与 Worker 的真实运行状态。"""
    runtime = await asyncio.to_thread(get_asr_runtime_status)
    return _asr_control_response(db, runtime)


@router.post("/asr-control/{enabled}", response_model=AsrControlResponse)
async def set_asr_control(enabled: bool, db: Session = Depends(get_db)):
    """按需启停 ASR，关闭时释放 FunASR 模型占用的内存。"""
    processing_count = db.query(AsrTask).filter(AsrTask.status == "processing").count()
    if not enabled and processing_count:
        raise HTTPException(409, f"当前有 {processing_count} 个话术任务正在生成，请等待完成后再关闭 ASR")
    try:
        runtime = await asyncio.to_thread(start_asr_runtime if enabled else stop_asr_runtime)
    except (OSError, subprocess.SubprocessError) as exc:
        raise HTTPException(500, f"ASR 服务{'启动' if enabled else '停止'}失败: {str(exc)}") from exc
    message = "ASR 话术服务已开启" if runtime["enabled"] else "ASR 话术服务已关闭，模型内存已释放"
    return _asr_control_response(db, runtime, message)


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
    await browser_manager.start_qr_login(task.id, f"采集账号_{task.id}")

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
        account = None
        account_id = state.get("account_id")
        if account_id:
            account = db.query(ScraperAccount).get(account_id)
        if account is None:
            account_name = state.get("account_name") or f"采集账号_{task_id}"
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

    await browser_manager.start_qr_login(
        task.id,
        account.account_name or f"采集账号_{account_id}",
        account.id,
    )

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


# ===== 刷新数据采集 =====
@router.post("/collect-all", response_model=CollectAllResponse)
async def manual_collect_all(db: Session = Depends(get_db)):
    """刷新全部主播、直播场次及场次详情数据。"""
    if scheduler_manager.running:
        raise HTTPException(409, "直播监控运行中，请先停止监控再刷新数据采集")
    existing = db.query(ScraperTask).filter(
        ScraperTask.task_type == "collect_all",
        ScraperTask.status == "running",
    ).first()
    if existing:
        raise HTTPException(409, f"刷新数据采集任务 #{existing.id} 正在运行，请勿重复提交")

    account = db.query(ScraperAccount).filter(
        ScraperAccount.login_status == "logged_in"
    ).order_by(ScraperAccount.last_login_at.desc()).first()
    task = ScraperTask(
        account_id=account.id if account else None,
        task_type="collect_all",
        status="running",
        started_at=datetime.utcnow(),
    )
    db.add(task)
    db.commit()

    def update_progress(stage, percent, current, total, message, details=None):
        details = details or {}
        task.progress_stage = stage
        task.progress_percent = max(0, min(100, int(percent)))
        task.progress_current = max(0, int(current or 0))
        task.progress_total = max(0, int(total or 0))
        task.progress_message = str(message)[:500]
        anchor_count = details.get("anchor_count", details.get("enterprise_anchor_count"))
        session_count = details.get(
            "discovered_session_count",
            details.get("enterprise_session_discovered_count"),
        )
        if anchor_count is not None:
            task.collected_anchor_count = max(0, int(anchor_count))
        if session_count is not None:
            task.collected_session_count = max(0, int(session_count))
        field_sources = {
            "new_session_count": ("session_count", "enterprise_session_synced_count"),
            "mapped_session_count": ("profile_count", "anchor_profile_synced_count"),
            "checked_detail_count": ("checked_count", "history_detail_checked_count"),
            "refreshed_detail_count": ("enriched_count", "history_detail_synced_count"),
            "failed_detail_count": ("failed_count", "history_detail_failed_count"),
            "remaining_detail_count": ("remaining_count", "history_detail_remaining_count"),
        }
        for task_field, source_keys in field_sources.items():
            value = next((details[key] for key in source_keys if details.get(key) is not None), None)
            if value is not None:
                setattr(task, task_field, max(0, int(value)))
        db.add(
            ScraperLog(
                task_id=task.id,
                level="info",
                message=message,
                raw_json={
                    "stage": stage,
                    "event": "progress",
                    "progress_percent": task.progress_percent,
                    "progress_current": task.progress_current,
                    "progress_total": task.progress_total,
                    "collected_anchor_count": task.collected_anchor_count,
                    "collected_session_count": task.collected_session_count,
                    "new_session_count": task.new_session_count,
                    "mapped_session_count": task.mapped_session_count,
                    "checked_detail_count": task.checked_detail_count,
                    "refreshed_detail_count": task.refreshed_detail_count,
                    "failed_detail_count": task.failed_detail_count,
                    "remaining_detail_count": task.remaining_detail_count,
                    "details": details,
                },
            )
        )
        db.commit()

    try:
        result = await collect_all(db, task_id=task.id, progress_callback=update_progress)
        task.status = "completed" if result.get("collected_rooms", 0) else "failed"
        if task.status == "failed":
            task.error_message = result.get("message") or "未采集到房间数据"
            task.progress_message = task.error_message
        return result
    except Exception as exc:
        task.status = "failed"
        task.error_message = str(exc)[:2000]
        task.progress_stage = "failed"
        task.progress_message = "采集任务执行失败"
        db.add(
            ScraperLog(
                task_id=task.id,
                level="error",
                message=f"刷新数据采集任务失败: {str(exc)}",
                raw_json={
                    "stage": "failed",
                    "event": "task_failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:2000],
                },
            )
        )
        raise
    finally:
        task.completed_at = datetime.utcnow()
        if task.status == "completed":
            task.progress_percent = 100
        db.commit()
