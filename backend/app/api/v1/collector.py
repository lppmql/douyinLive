"""Phase 3: 采集状态 & 扫码登录 API"""
import asyncio
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.core.config import settings
from app.models.live_sessions import LiveSession
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
    LoginQRResponse,
    LoginStatusResponse,
    AccountHealthResponse,
    AsrControlResponse,
    CollectAllResponse,
    AccountDeleteResponse,
    LogsClearResponse,
    CollectorControlCenterResponse,
    CollectorTaskActionResponse,
    UnifiedTaskResponse,
)
from app.services.collector.browser import browser_manager
from app.services.collector.browser import STORAGE_DIR
from app.services.collector.manual_collect import collect_all
from app.services.collector.scheduler import scheduler_manager
from app.services.asr.control import get_asr_runtime_status
from app.services.asr.queue import queue_session_transcription
from app.services.collector.log_service import serialize_collector_logs
from app.services.tasks.control import collector_task_control
from app.services.tasks.status import build_control_center
from app.services.tasks.views import get_unified_task, list_unified_tasks
from app.services.tasks.module_service import MODULE_KEYS, collector_module_service
from app.services.resources.system_usage import get_system_usage
from app.services.tasks.runtime import (
    current_worker_id,
    ensure_task_identity,
    publish_task_event,
    touch_task,
)
from app.models.asr_tasks import AsrTask
from app.core.status import TaskStatus

router = APIRouter(prefix="/collector", tags=["数据采集"])


def _build_control_center_snapshot(
    asr_runtime: dict,
    resource_usage: dict,
) -> dict:
    """在线程中独立读取状态，复杂统计不会卡住其他 FastAPI 请求。"""
    db = SessionLocal()
    try:
        return build_control_center(db, asr_runtime, resource_usage)
    finally:
        db.close()


def _collector_heartbeat_loop(task_id: int, stop_event: threading.Event) -> None:
    """长任务独立心跳，避免页面等待阶段被误判为卡死。"""
    while not stop_event.wait(30):
        heartbeat_db = SessionLocal()
        try:
            heartbeat_db.query(ScraperTask).filter(
                ScraperTask.id == task_id,
                ScraperTask.status == TaskStatus.RUNNING,
            ).update({ScraperTask.heartbeat_at: datetime.utcnow()}, synchronize_session=False)
            heartbeat_db.commit()
        except Exception:
            heartbeat_db.rollback()
        finally:
            heartbeat_db.close()


def _collection_succeeded(result: dict) -> bool:
    """企业主播、场次或详情任一真实链路成功，都不应被入口房间失败覆盖。"""
    return any(
        int(result.get(key) or 0) > 0
        for key in (
            "collected_rooms",
            "enterprise_anchor_count",
            "enterprise_session_discovered_count",
            "history_detail_synced_count",
        )
    )


async def _change_asr_service(enabled: bool) -> tuple[dict, str]:
    """兼容旧 ASR 接口，并统一写入新的持久开关状态。"""
    try:
        if enabled:
            _task, message = await collector_module_service.enable("asr")
        else:
            _stopped_count, message = await collector_module_service.disable("asr")
        runtime = await asyncio.to_thread(get_asr_runtime_status)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        raise HTTPException(500, f"ASR 服务{'启动' if enabled else '停止'}失败: {str(exc)}") from exc
    return runtime, message


def _task_action_payload(db: Session, source: str, task_id: int, message: str) -> dict:
    # MySQL 默认的可重复读事务看不到另一个会话刚创建的任务。
    # 先结束当前只读事务，再读取任务，保证开关响应立即带回任务编号和进度。
    db.commit()
    db.expire_all()
    return {
        "success": True,
        "message": message,
        "task": get_unified_task(db, source, task_id),
    }


# ===== 采集器状态 =====
@router.get("/status", response_model=CollectorStatusResponse)
def get_collector_status(db: Session = Depends(get_db)):
    """获取采集器整体状态"""
    active_count = db.query(ScraperTask).filter(ScraperTask.status == TaskStatus.RUNNING).count()
    default_account = db.query(ScraperAccount).order_by(ScraperAccount.last_login_at.desc()).first()
    return CollectorStatusResponse(
        connected=default_account is not None,
        active_task_count=active_count,
        default_account=ScraperAccountResponse.model_validate(default_account) if default_account else None,
    )


# ===== 统一控制中心 =====
@router.get("/control-center", response_model=CollectorControlCenterResponse)
async def get_control_center():
    """一次返回补齐动作、长期服务、后台自动同步和任务数量，供页面静默轮询。"""
    runtime, resource_usage = await asyncio.gather(
        asyncio.to_thread(get_asr_runtime_status),
        asyncio.to_thread(get_system_usage),
    )
    return await asyncio.to_thread(
        _build_control_center_snapshot,
        runtime,
        resource_usage,
    )


@router.get("/task-queue", response_model=list[UnifiedTaskResponse])
def get_task_queue(
    limit: int = Query(100, ge=1, le=300),
    db: Session = Depends(get_db),
):
    """返回采集、AI、知识库、DataEase 和逐场 ASR 的统一任务队列。"""
    return list_unified_tasks(db, limit=limit)


@router.post("/modules/{module_key}/start", response_model=CollectorTaskActionResponse)
async def start_collector_module(module_key: str, db: Session = Depends(get_db)):
    """开启长期运行服务，并立即从最新及正在直播的场次开始检查。"""
    if module_key not in MODULE_KEYS:
        raise HTTPException(404, "采集处理模块不存在")
    if module_key == "monitor":
        running_refresh = db.query(ScraperTask).filter(
            ScraperTask.task_type == "collect_all",
            ScraperTask.status == TaskStatus.RUNNING,
        ).first()
        if not settings.monitor_mock_enabled and not running_refresh:
            context, valid, message = await scheduler_manager.run_serialized_browser_operation(
                browser_manager.get_logged_in_context
            )
            if not valid or not context:
                raise HTTPException(409, message or "采集账号登录状态不可用，请重新扫码")
    await collector_task_control.start()
    try:
        task, message = await collector_module_service.enable(module_key)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if not task:
        return {"success": True, "message": message, "task": None}
    return _task_action_payload(db, "scraper", task.id, message)


@router.post("/modules/{module_key}/stop", response_model=CollectorTaskActionResponse)
async def stop_collector_module(module_key: str, db: Session = Depends(get_db)):
    """彻底关闭模块，不再创建新任务，并在安全点释放专属资源。"""
    del db
    if module_key not in MODULE_KEYS:
        raise HTTPException(404, "采集处理模块不存在")
    try:
        _stopped_count, message = await collector_module_service.disable(module_key)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"success": True, "message": message, "task": None}


@router.post("/task-queue/{source}/{task_id}/stop", response_model=CollectorTaskActionResponse)
def stop_queue_task(source: str, task_id: int, db: Session = Depends(get_db)):
    """停止任务队列中的单个任务；ASR 运行任务会在当前音频处理安全点退出。"""
    if source == "scraper":
        try:
            task = collector_task_control.request_cancel(task_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return _task_action_payload(db, source, task.id, "停止请求已提交")

    if source != "asr":
        raise HTTPException(404, "任务来源不存在")
    task = db.get(AsrTask, task_id)
    if not task:
        raise HTTPException(404, "ASR 任务不存在")
    if task.status == TaskStatus.QUEUED:
        task.status = TaskStatus.CANCELLED
        task.cancel_requested_at = datetime.utcnow()
        task.completed_at = datetime.utcnow()
        task.error_message = "用户在执行前停止任务"
    elif task.status == TaskStatus.PROCESSING:
        task.cancel_requested_at = datetime.utcnow()
        task.error_message = "正在等待当前音频处理安全点后停止"
    else:
        raise HTTPException(409, "只有排队中或转写中的任务可以停止")
    touch_task(task)
    db.commit()
    publish_task_event("asr", task, "cancel_requested", {})
    return _task_action_payload(db, source, task.id, "ASR 停止请求已提交")


@router.post("/task-queue/{source}/{task_id}/retry", response_model=CollectorTaskActionResponse)
def retry_queue_task(source: str, task_id: int, db: Session = Depends(get_db)):
    """重试失败或已停止任务，并复用已完成的真实数据与音频分片。"""
    if source == "scraper":
        try:
            task = collector_task_control.retry(task_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return _task_action_payload(db, source, task.id, f"已创建重试任务 #{task.id}")

    if source != "asr":
        raise HTTPException(404, "任务来源不存在")
    task = db.get(AsrTask, task_id)
    if not task:
        raise HTTPException(404, "ASR 任务不存在")
    if task.status not in (TaskStatus.FAILED, TaskStatus.CANCELLED):
        raise HTTPException(409, "只有失败或已停止的 ASR 任务可以重试")
    session = db.get(LiveSession, task.session_id)
    if not session:
        raise HTTPException(404, "ASR 任务关联的直播场次不存在")
    try:
        retried_task, _created = queue_session_transcription(db, session)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    publish_task_event("asr", retried_task, "retried", {"session_id": session.id})
    return _task_action_payload(db, source, retried_task.id, "ASR 任务已从断点重新排队")


# ===== 账号管理 =====
@router.get("/accounts", response_model=list[ScraperAccountResponse])
def list_accounts(db: Session = Depends(get_db)):
    """获取所有采集账号"""
    return db.query(ScraperAccount).order_by(ScraperAccount.id.desc()).all()


@router.get("/accounts/{account_id}", response_model=ScraperAccountResponse)
def get_account(account_id: int, db: Session = Depends(get_db)):
    """获取单个账号详情"""
    account = db.get(ScraperAccount, account_id)
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
    account = db.get(ScraperAccount, account_id)
    if not account:
        raise HTTPException(404, "账号不存在")
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(account, key, val)
    db.commit()
    db.refresh(account)
    return account


@router.delete("/accounts/{account_id}", response_model=AccountDeleteResponse)
async def delete_account(account_id: int, db: Session = Depends(get_db)):
    """删除采集账号，并保留历史采集任务与业务数据。"""
    account = db.get(ScraperAccount, account_id)
    if not account:
        raise HTTPException(404, "账号不存在")

    running_task_count = db.query(ScraperTask).filter(
        ScraperTask.account_id == account_id,
        ScraperTask.status == TaskStatus.RUNNING,
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
    account = db.get(ScraperAccount, account_id)
    if not account:
        raise HTTPException(404, "账号不存在")
    if db.query(ScraperTask).filter(
        ScraperTask.status == TaskStatus.RUNNING,
        ScraperTask.task_type.in_(("collect_all", "login")),
    ).count():
        raise HTTPException(409, "当前有刷新采集或扫码登录任务运行，请等待任务结束后再检查账号")

    valid, message = await scheduler_manager.run_serialized_browser_operation(
        lambda: browser_manager.check_account_health(account)
    )
    account.login_status = "logged_in" if valid else "expired"
    account.cookie_checked_at = datetime.utcnow()
    db.commit()
    return AccountHealthResponse(
        account_id=account.id,
        valid=valid,
        login_status=account.login_status,
        cookie_status=getattr(account, "cookie_status", "valid" if valid else "expired"),
        douyin_nickname=getattr(account, "douyin_nickname", None),
        douyin_id=getattr(account, "douyin_id", None),
        checked_at=account.cookie_checked_at,
        message=message,
    )


def _asr_control_response(db: Session, runtime: dict, message: str = "") -> AsrControlResponse:
    queued_count = db.query(AsrTask).filter(AsrTask.status == TaskStatus.QUEUED).count()
    processing_count = db.query(AsrTask).filter(AsrTask.status == "processing").count()
    postprocess_counts = {
        status: db.query(AsrTask).filter(
            AsrTask.status == TaskStatus.COMPLETED,
            AsrTask.postprocess_status == status,
        ).count()
        for status in (TaskStatus.PENDING, "processing", TaskStatus.COMPLETED, TaskStatus.FAILED)
    }
    return AsrControlResponse(
        enabled=runtime["enabled"],
        engine_running=runtime["engine_running"],
        worker_running=runtime["worker_running"],
        queued_count=queued_count,
        processing_count=processing_count,
        postprocess_pending_count=postprocess_counts[TaskStatus.PENDING],
        postprocess_processing_count=postprocess_counts["processing"],
        postprocess_completed_count=postprocess_counts[TaskStatus.COMPLETED],
        postprocess_failed_count=postprocess_counts[TaskStatus.FAILED],
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
    runtime, message = await _change_asr_service(enabled)
    return _asr_control_response(db, runtime, message)


# ===== 扫码登录 =====
@router.post("/accounts/login", response_model=LoginStartResponse)
async def start_login(db: Session = Depends(get_db)):
    """启动扫码登录（后台打开有头浏览器）"""
    task = ScraperTask(task_type="login", status=TaskStatus.RUNNING, started_at=datetime.utcnow())
    ensure_task_identity(task, "scraper-login")
    task.retry_count = 1
    touch_task(task, current_worker_id("collector-api"))
    # 先 flush 获取 ID
    db.add(task)
    db.commit()
    db.refresh(task)
    publish_task_event("scraper", task, "started", {"task_type": "login"})

    # 在后台启动浏览器扫码
    await browser_manager.start_qr_login(task.id, f"采集账号_{task.id}")

    return LoginStartResponse(task_id=task.id, message="请使用抖音扫描二维码")


@router.get("/login-tasks/{task_id}/qr", response_model=LoginQRResponse)
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
        task = db.get(ScraperTask, task_id)
        if not task:
            raise HTTPException(404, "登录任务不存在")
        return LoginStatusResponse(status=task.status, message="任务已结束")

    # 登录成功 → 查找已保存的账号记录（_qr_login_worker 已直接写入）
    if state["status"] == "success":
        account = None
        account_id = state.get("account_id")
        if account_id:
            account = db.get(ScraperAccount, account_id)
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
    account = db.get(ScraperAccount, account_id)
    if not account:
        raise HTTPException(404, "账号不存在")

    task = ScraperTask(task_type="login", status=TaskStatus.RUNNING)
    ensure_task_identity(task, "scraper-relogin")
    task.retry_count = 1
    task.started_at = datetime.utcnow()
    touch_task(task, current_worker_id("collector-api"))
    db.add(task)
    db.commit()
    db.refresh(task)
    publish_task_event("scraper", task, "started", {"task_type": "login", "account_id": account_id})

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
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """获取采集日志"""
    q = db.query(ScraperLog)
    if task_id:
        q = q.filter(ScraperLog.task_id == task_id)
    if level:
        q = q.filter(ScraperLog.level == level)
    rows = q.order_by(ScraperLog.id.desc()).limit(limit).all()
    return serialize_collector_logs(db, rows)


@router.delete("/logs", response_model=LogsClearResponse)
def clear_logs(db: Session = Depends(get_db)):
    """清空现有采集日志，不删除采集任务和业务数据。"""
    try:
        deleted_count = db.query(ScraperLog).delete(synchronize_session=False)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, "清空采集日志失败，请稍后重试") from exc
    return {"message": "采集日志已清空", "deleted_count": deleted_count}


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
    existing = db.query(ScraperTask).filter(
        ScraperTask.task_type == "collect_all",
        ScraperTask.status == TaskStatus.RUNNING,
    ).first()
    if existing:
        raise HTTPException(409, f"刷新数据采集任务 #{existing.id} 正在运行，请勿重复提交")

    account = db.query(ScraperAccount).filter(
        ScraperAccount.login_status == "logged_in"
    ).order_by(ScraperAccount.last_login_at.desc()).first()
    task = ScraperTask(
        account_id=account.id if account else None,
        task_type="collect_all",
        status=TaskStatus.RUNNING,
        started_at=datetime.utcnow(),
    )
    ensure_task_identity(task, "scraper-collect-all")
    task.retry_count = 1
    touch_task(task, current_worker_id("collector-api"))
    db.add(task)
    db.commit()
    db.refresh(task)
    publish_task_event("scraper", task, "started", {"task_type": "collect_all"})
    heartbeat_stop = threading.Event()
    heartbeat_thread = threading.Thread(
        target=_collector_heartbeat_loop,
        args=(task.id, heartbeat_stop),
        name=f"collector-heartbeat-{task.id}",
        daemon=True,
    )
    heartbeat_thread.start()

    def update_progress(stage, percent, current, total, message, details=None):
        details = details or {}
        task.progress_stage = stage
        task.progress_percent = max(0, min(100, int(percent)))
        task.progress_current = max(0, int(current or 0))
        task.progress_total = max(0, int(total or 0))
        task.progress_message = str(message)[:500]
        touch_task(task)
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
        publish_task_event(
            "scraper",
            task,
            "progress",
            {
                "stage": stage,
                "percent": task.progress_percent,
                "current": task.progress_current,
                "total": task.progress_total,
                "message": task.progress_message,
            },
        )

    try:
        await scheduler_manager.wait_for_collection_slot()
        result = await collect_all(db, task_id=task.id, progress_callback=update_progress)
        task.status = TaskStatus.COMPLETED if _collection_succeeded(result) else TaskStatus.FAILED
        if task.status == TaskStatus.FAILED:
            task.error_message = result.get("message") or "未采集到房间数据"
            task.progress_message = task.error_message
        return result
    except Exception as exc:
        from app.services.collector.manual_collect import _sanitize_collector_error

        compact_error = _sanitize_collector_error(exc)
        task.status = TaskStatus.FAILED
        task.error_message = compact_error
        task.progress_stage = TaskStatus.FAILED
        task.progress_message = "采集任务执行失败"
        db.add(
            ScraperLog(
                task_id=task.id,
                level="error",
                message=f"刷新数据采集任务失败: {compact_error}",
                raw_json={
                    "stage": TaskStatus.FAILED,
                    "event": "task_failed",
                    "error_type": type(exc).__name__,
                    "error": compact_error,
                },
            )
        )
        raise
    finally:
        heartbeat_stop.set()
        await asyncio.to_thread(heartbeat_thread.join, 5)
        task.completed_at = datetime.utcnow()
        touch_task(task)
        if task.status == TaskStatus.COMPLETED:
            task.progress_percent = 100
        db.commit()
        publish_task_event(
            "scraper",
            task,
            TaskStatus.COMPLETED if task.status == TaskStatus.COMPLETED else TaskStatus.FAILED,
            {
                "stage": task.progress_stage,
                "message": task.progress_message or task.error_message or "",
                "anchor_count": task.collected_anchor_count,
                "session_count": task.collected_session_count,
            },
        )
        scheduler_manager.resume_after_collection()
