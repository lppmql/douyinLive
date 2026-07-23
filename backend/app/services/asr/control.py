"""本地 ASR 服务启停控制，供管理页面按需释放模型资源。"""
import gzip
import os
import shlex
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path

from app.core.config import PROJECT_ROOT
from app.core.config import settings


BACKEND_DIR = PROJECT_ROOT / "backend"
ASR_LOG_PATH = PROJECT_ROOT / "data" / "logs" / "asr_worker.log"
ASR_LOG_ARCHIVE_PATH = PROJECT_ROOT / "data" / "logs" / "asr_worker.legacy.log.gz"


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


def _engine_running() -> bool:
    """用实际服务端口判断模型是否可访问，避免页面轮询每次启动 Docker CLI。"""
    try:
        with socket.create_connection((settings.FUNASR_HOST, settings.FUNASR_PORT), timeout=0.3):
            return True
    except OSError:
        return False


def get_asr_runtime_status() -> dict:
    worker_pids = _worker_pids()
    engine_running = _engine_running()
    return {
        "enabled": engine_running and bool(worker_pids),
        "engine_running": engine_running,
        "worker_running": bool(worker_pids),
        "worker_pids": worker_pids,
    }


def start_asr_runtime() -> dict:
    docker = _docker_bin()
    subprocess.run(
        [docker, "compose", "--profile", "funasr", "up", "-d", "funasr"],
        cwd=PROJECT_ROOT,
        check=True,
    )
    if not _worker_pids():
        ASR_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _archive_oversized_log()
        worker_command = [str(BACKEND_DIR / ".venv" / "bin" / "python"), "-m", "workers.asr_worker"]
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
    return get_asr_runtime_status()


def stop_asr_runtime() -> dict:
    for pid in _worker_pids():
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 8
    while _worker_pids() and time.monotonic() < deadline:
        time.sleep(0.2)
    subprocess.run([_docker_bin(), "stop", "douyin_live_funasr"], check=False, capture_output=True)
    return get_asr_runtime_status()
