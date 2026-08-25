"""本地 ASR 服务启停控制，供管理页面按需释放模型资源。"""
import gzip
import json
import os
import shlex
import shutil
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path

from app.core.config import PROJECT_ROOT
from app.core.config import settings


BACKEND_DIR = PROJECT_ROOT / "backend"
ASR_LOG_PATH = PROJECT_ROOT / "data" / "logs" / "asr_worker.log"
ASR_LOG_ARCHIVE_PATH = PROJECT_ROOT / "data" / "logs" / "asr_worker.legacy.log.gz"
ASR_RUNTIME_STATE_PATH = PROJECT_ROOT / "data" / "runtime" / "asr-worker.json"
ASR_WORKER_HEARTBEAT_TIMEOUT_SECONDS = 20
_ASR_RUNTIME_LOCK = threading.Lock()


def _archive_oversized_log() -> None:
    """首次启用轮转前压缩旧大日志，既保留排障记录，也立即释放磁盘。"""
    if not ASR_LOG_PATH.exists() or ASR_LOG_PATH.stat().st_size <= 20 * 1024 * 1024:
        return
    temporary_path = ASR_LOG_ARCHIVE_PATH.with_suffix(".gz.tmp")
    with ASR_LOG_PATH.open("rb") as source, gzip.open(temporary_path, "wb", compresslevel=6) as target:
        shutil.copyfileobj(source, target, length=1024 * 1024)
    temporary_path.replace(ASR_LOG_ARCHIVE_PATH)
    ASR_LOG_PATH.unlink(missing_ok=True)


def _docker_bin() -> str:
    docker = shutil.which("docker")
    if docker:
        return docker
    fallback = Path("/usr/local/bin/docker")
    if fallback.exists():
        return str(fallback)
    raise RuntimeError("未找到 Docker 命令，请先启动 Docker Desktop")


def _worker_pids() -> list[int]:
    """只识别真实 Python Worker，避免 macOS 的 pgrep 把查询进程自身算进去。"""
    result = subprocess.run(
        ["ps", "-axo", "pid=,comm=,args="],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    worker_pids = []
    for line in result.stdout.splitlines():
        columns = line.strip().split(maxsplit=2)
        if len(columns) < 3 or not columns[0].isdigit():
            continue
        try:
            command = shlex.split(columns[2])
        except ValueError:
            continue
        if not command or "python" not in Path(command[0]).name.lower():
            continue
        if any(
            command[index] == "-m" and command[index + 1] == "workers.asr_worker"
            for index in range(len(command) - 1)
        ):
            worker_pids.append(int(columns[0]))
    return worker_pids


def write_asr_worker_heartbeat(worker_id: str, status: str = "running") -> None:
    """Worker 写入独立心跳，解决“进程仍在但事件循环已停止”的误判。"""
    ASR_RUNTIME_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": os.getpid(),
        "worker_id": worker_id,
        "status": status,
        "updated_at": time.time(),
    }
    temporary_path = ASR_RUNTIME_STATE_PATH.with_suffix(f".{os.getpid()}.tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    temporary_path.replace(ASR_RUNTIME_STATE_PATH)


def clear_asr_worker_heartbeat(pid: int | None = None) -> None:
    """只清理指定 Worker 自己的心跳，避免旧进程删除新 Worker 状态。"""
    if not ASR_RUNTIME_STATE_PATH.exists():
        return
    if pid is not None:
        try:
            payload = json.loads(ASR_RUNTIME_STATE_PATH.read_text(encoding="utf-8"))
            if int(payload.get("pid") or 0) != int(pid):
                return
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
    ASR_RUNTIME_STATE_PATH.unlink(missing_ok=True)


def _read_asr_worker_heartbeat() -> dict:
    try:
        payload = json.loads(ASR_RUNTIME_STATE_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def _heartbeat_snapshot(worker_pids: list[int]) -> dict:
    payload = _read_asr_worker_heartbeat()
    heartbeat_pid = int(payload.get("pid") or 0)
    updated_at = float(payload.get("updated_at") or 0)
    age_seconds = max(0.0, time.time() - updated_at) if updated_at else None
    worker_healthy = bool(
        heartbeat_pid in worker_pids
        and payload.get("status") == "running"
        and age_seconds is not None
        and age_seconds <= ASR_WORKER_HEARTBEAT_TIMEOUT_SECONDS
    )
    return {
        "worker_healthy": worker_healthy,
        "worker_status": (
            "healthy" if worker_healthy else "stale" if worker_pids else "stopped"
        ),
        "worker_heartbeat_at": updated_at or None,
        "worker_heartbeat_age_seconds": (
            round(age_seconds, 1) if age_seconds is not None else None
        ),
    }


def _terminate_worker_processes(grace_seconds: float = 8) -> list[int]:
    """先优雅停止，超时后只强制清理已确认的 ASR Worker 进程。"""
    target_pids = _worker_pids()
    for pid in target_pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + max(0, grace_seconds)
    while time.monotonic() < deadline:
        remaining = set(_worker_pids()).intersection(target_pids)
        if not remaining:
            break
        time.sleep(0.2)
    remaining = sorted(set(_worker_pids()).intersection(target_pids))
    forced_pids = remaining[:]
    for pid in remaining:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    kill_deadline = time.monotonic() + 2
    while remaining and time.monotonic() < kill_deadline:
        time.sleep(0.1)
        remaining = sorted(set(_worker_pids()).intersection(target_pids))
    clear_asr_worker_heartbeat()
    return forced_pids


def _engine_running() -> bool:
    """用实际服务端口判断模型是否可访问，避免页面轮询每次启动 Docker CLI。"""
    try:
        with socket.create_connection((settings.FUNASR_HOST, settings.FUNASR_PORT), timeout=0.3):
            return True
    except OSError:
        return False


def is_asr_engine_running() -> bool:
    """供剪辑前置检查复用实际端口探测，不触发 Docker 启停操作。"""
    return _engine_running()


def get_asr_runtime_status() -> dict:
    worker_pids = _worker_pids()
    engine_running = _engine_running()
    heartbeat = _heartbeat_snapshot(worker_pids)
    worker_healthy = heartbeat["worker_healthy"]
    if worker_healthy:
        message = "ASR Worker 心跳正常"
    elif worker_pids:
        message = "检测到无心跳的 ASR Worker，系统将在下次启动检查时自动恢复"
    else:
        message = "ASR Worker 未运行"
    return {
        "enabled": engine_running and worker_healthy,
        "engine_running": engine_running,
        "worker_running": bool(worker_pids),
        "worker_pids": worker_pids,
        **heartbeat,
        "message": message,
    }


def start_asr_runtime() -> dict:
    with _ASR_RUNTIME_LOCK:
        docker = _docker_bin()
        subprocess.run(
            [docker, "compose", "--profile", "funasr", "up", "-d", "funasr"],
            cwd=PROJECT_ROOT,
            check=True,
        )
        runtime = get_asr_runtime_status()
        if runtime["worker_running"] and not runtime["worker_healthy"]:
            _terminate_worker_processes(grace_seconds=3)
        if not _worker_pids():
            ASR_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            _archive_oversized_log()
            worker_command = [
                str(BACKEND_DIR / ".venv" / "bin" / "python"),
                "-m",
                "workers.asr_worker",
            ]
            nice = shutil.which("nice")
            if nice:
                worker_command = [nice, "-n", "10", *worker_command]
            worker_env = os.environ.copy()
            worker_env["ASR_WORKER_LOG_PATH"] = str(ASR_LOG_PATH)
            subprocess.Popen(
                worker_command,
                cwd=BACKEND_DIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
                env=worker_env,
                start_new_session=True,
            )
        deadline = time.monotonic() + 12
        runtime = get_asr_runtime_status()
        while not runtime["worker_healthy"] and time.monotonic() < deadline:
            time.sleep(0.2)
            runtime = get_asr_runtime_status()
        if not runtime["worker_healthy"]:
            raise RuntimeError(runtime["message"] or "ASR Worker 启动后没有心跳")
        return runtime


def stop_asr_runtime() -> dict:
    with _ASR_RUNTIME_LOCK:
        _terminate_worker_processes(grace_seconds=8)
        subprocess.run(
            [_docker_bin(), "stop", "douyin_live_funasr"],
            check=False,
            capture_output=True,
        )
        return get_asr_runtime_status()
