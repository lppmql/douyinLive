"""低开销采样电脑和本项目进程的真实资源占用。"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil

from app.core.config import PROJECT_ROOT, settings


_cache_lock = threading.Lock()
_cached_snapshot: dict[str, Any] | None = None
_cached_at = 0.0
_cached_docker: dict[str, Any] | None = None
_cached_docker_at = 0.0
_process_cpu_samples: dict[int, tuple[float, float]] = {}

# 第一次调用 cpu_percent 只建立基线，提前初始化可让页面首次采样更接近真实值。
psutil.cpu_percent(interval=None)


def _parse_size(value: str) -> int:
    """把 Docker 返回的 674MiB、1.8GiB 转成字节。"""
    text = str(value or "").strip().replace(" ", "")
    units = {
        "B": 1,
        "KiB": 1024,
        "MiB": 1024**2,
        "GiB": 1024**3,
        "TiB": 1024**4,
        "kB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
    }
    for unit in sorted(units, key=len, reverse=True):
        if text.endswith(unit):
            try:
                return int(float(text[: -len(unit)]) * units[unit])
            except ValueError:
                return 0
    return 0


def _funasr_port_running() -> bool:
    """直接探测 ASR 服务端口，Docker 命令变慢时也能准确显示运行状态。"""
    try:
        with socket.create_connection((settings.FUNASR_HOST, settings.FUNASR_PORT), timeout=0.3):
            return True
    except OSError:
        return False


def _docker_asr_usage(now: float) -> dict[str, Any]:
    """缓存 FunASR 容器指标，避免页面每 5 秒都启动 Docker CLI。"""
    global _cached_docker, _cached_docker_at
    if _cached_docker is not None and now - _cached_docker_at < 15:
        return _cached_docker

    result = {
        "key": "funasr",
        "label": "FunASR 模型",
        "running": _funasr_port_running(),
        "cpu_percent": 0.0,
        "memory_bytes": 0,
    }
    docker = shutil.which("docker")
    if docker:
        try:
            completed = subprocess.run(
                [docker, "stats", "--no-stream", "--format", "{{json .}}", "douyin_live_funasr"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            lines = completed.stdout.strip().splitlines()
            if completed.returncode == 0 and lines:
                payload = json.loads(lines[-1])
                memory_used = str(payload.get("MemUsage") or "").split("/", 1)[0].strip()
                running = result["running"] or int(payload.get("PIDs") or 0) > 0
                result.update(
                    running=running,
                    cpu_percent=(
                        float(str(payload.get("CPUPerc") or "0").rstrip("%") or 0)
                        if running
                        else 0
                    ),
                    memory_bytes=_parse_size(memory_used) if running else 0,
                )
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError):
            pass

    _cached_docker = result
    _cached_docker_at = now
    return result


def _process_kind(process: psutil.Process, current_pid: int) -> str | None:
    """按命令行识别本项目进程，避免把其他应用算进来。"""
    if process.pid == current_pid:
        return "backend"
    try:
        command = " ".join(process.cmdline()).lower()
        name = process.name().lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None
    if "workers.asr_worker" in command:
        return "asr_worker"
    if "ffmpeg" in name or "ffmpeg" in command:
        return "ffmpeg"
    if "chromium" in command or "chrome" in name or "ms-playwright" in command:
        return "chromium"
    return None


def _process_components() -> list[dict[str, Any]]:
    """汇总后端及其子进程，子进程退出时自动从下一次采样中消失。"""
    labels = {
        "backend": "后端服务",
        "chromium": "Chromium 采集",
        "asr_worker": "ASR Worker",
        "ffmpeg": "FFmpeg 音频",
    }
    totals = {key: {"cpu_percent": 0.0, "memory_bytes": 0, "running": False} for key in labels}
    global _process_cpu_samples
    current = psutil.Process(os.getpid())
    sampled_at = time.monotonic()
    next_cpu_samples: dict[int, tuple[float, float]] = {}
    for process in [current, *current.children(recursive=True)]:
        kind = _process_kind(process, current.pid)
        if not kind:
            continue
        try:
            cpu_times = process.cpu_times()
            cpu_seconds = float(cpu_times.user + cpu_times.system)
            previous = _process_cpu_samples.get(process.pid)
            process_cpu = 0.0
            if previous and sampled_at > previous[0]:
                process_cpu = max(0.0, (cpu_seconds - previous[1]) / (sampled_at - previous[0]) * 100)
            next_cpu_samples[process.pid] = (sampled_at, cpu_seconds)
            totals[kind]["cpu_percent"] += process_cpu
            totals[kind]["memory_bytes"] += max(0, int(process.memory_info().rss))
            totals[kind]["running"] = process.is_running()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    _process_cpu_samples = next_cpu_samples
    return [
        {
            "key": key,
            "label": labels[key],
            "running": bool(value["running"]),
            "cpu_percent": round(float(value["cpu_percent"]), 1),
            "memory_bytes": int(value["memory_bytes"]),
        }
        for key, value in totals.items()
    ]


def _pressure(cpu_percent: float, memory_percent: float) -> tuple[str, str]:
    if memory_percent >= settings.RESOURCE_CRITICAL_MEMORY_PERCENT:
        return "critical", "内存压力过高，新批次已延后，请关闭暂时不用的模块"
    if cpu_percent >= settings.RESOURCE_HIGH_CPU_PERCENT or memory_percent >= settings.RESOURCE_HIGH_MEMORY_PERCENT:
        return "high", "电脑资源偏高，系统会自动降低新批次启动频率"
    return "normal", "资源状态正常，持续任务按设定频率运行"


def get_system_usage(force: bool = False) -> dict[str, Any]:
    """返回真实资源快照；短时间重复调用直接使用缓存。"""
    global _cached_snapshot, _cached_at
    now = time.monotonic()
    cache_seconds = max(2, settings.RESOURCE_SAMPLE_INTERVAL_SECONDS)
    with _cache_lock:
        if not force and _cached_snapshot is not None and now - _cached_at < cache_seconds:
            return dict(_cached_snapshot)

        cpu_percent = round(
            float(psutil.cpu_percent(interval=0.1 if _cached_snapshot is None else None)),
            1,
        )
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(str(Path(PROJECT_ROOT)))
        components = _process_components()
        components.append(_docker_asr_usage(now))
        app_memory_bytes = sum(int(item["memory_bytes"]) for item in components)
        pressure_level, pressure_message = _pressure(cpu_percent, float(memory.percent))
        snapshot = {
            "sampled_at": datetime.utcnow(),
            "cpu_percent": cpu_percent,
            "memory_percent": round(float(memory.percent), 1),
            "memory_used_bytes": int(memory.used),
            "memory_total_bytes": int(memory.total),
            "disk_used_percent": round(float(disk.percent), 1),
            "disk_free_bytes": int(disk.free),
            "app_memory_bytes": app_memory_bytes,
            "pressure_level": pressure_level,
            "pressure_message": pressure_message,
            "components": components,
        }
        _cached_snapshot = snapshot
        _cached_at = now
        return dict(snapshot)
