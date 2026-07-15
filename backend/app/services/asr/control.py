"""本地 ASR 服务启停控制，供管理页面按需释放模型资源。"""
import os
import shlex
import shutil
import signal
import subprocess
from pathlib import Path

from app.core.config import PROJECT_ROOT


BACKEND_DIR = PROJECT_ROOT / "backend"
ASR_LOG_PATH = PROJECT_ROOT / "data" / "logs" / "asr_worker.log"


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
    result = subprocess.run(
        [_docker_bin(), "inspect", "-f", "{{.State.Running}}", "douyin_live_funasr"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


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
        worker_command = [str(BACKEND_DIR / ".venv" / "bin" / "python"), "-m", "workers.asr_worker"]
        nice = shutil.which("nice")
        if nice:
            worker_command = [nice, "-n", "10", *worker_command]
        with ASR_LOG_PATH.open("ab") as log_file:
            subprocess.Popen(
                worker_command,
                cwd=BACKEND_DIR,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    return get_asr_runtime_status()


def stop_asr_runtime() -> dict:
    for pid in _worker_pids():
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    subprocess.run([_docker_bin(), "stop", "douyin_live_funasr"], check=False, capture_output=True)
    return get_asr_runtime_status()
