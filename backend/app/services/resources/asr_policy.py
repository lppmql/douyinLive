"""根据电脑实时资源为 ASR 计算并发和排队容量。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from app.core.config import settings


@dataclass(frozen=True)
class AsrResourcePlan:
    """一次资源采样对应的 ASR 调度决定。"""

    target_concurrency: int
    queue_capacity: int
    pressure_level: str
    pause_new_tasks: bool
    message: str


def build_asr_resource_plan(
    usage: dict[str, Any],
    *,
    cpu_count: int | None = None,
    max_concurrency: int | None = None,
) -> AsrResourcePlan:
    """资源充足时自动扩容，压力升高时在分片边界自动降速。"""
    pressure = str(usage.get("pressure_level") or "normal")
    cpu_percent = max(0.0, float(usage.get("cpu_percent") or 0))
    memory_percent = max(0.0, float(usage.get("memory_percent") or 0))
    ceiling = max(1, int(max_concurrency or settings.ASR_DYNAMIC_MAX_TASKS))
    available_cpus = max(1, int(cpu_count or os.cpu_count() or 1))

    if pressure == "critical" or memory_percent >= settings.RESOURCE_CRITICAL_MEMORY_PERCENT:
        return AsrResourcePlan(
            target_concurrency=0,
            queue_capacity=0,
            pressure_level="critical",
            pause_new_tasks=True,
            message="内存压力严重，ASR 已在安全分片边界暂停，资源恢复后自动继续",
        )

    if (
        pressure == "high"
        or cpu_percent >= settings.RESOURCE_HIGH_CPU_PERCENT
        or memory_percent >= settings.RESOURCE_HIGH_MEMORY_PERCENT
    ):
        return AsrResourcePlan(
            target_concurrency=1,
            queue_capacity=1,
            pressure_level="high",
            pause_new_tasks=False,
            message="电脑资源偏高，ASR 已自动降为单任务运行",
        )

    # 每个任务会启动一个 FFmpeg 音频管道。CPU、内存和核心数分别计算安全槽位，
    # 最后取最小值，资源富余时可突破旧版固定单并发，但不会无上限压垮电脑。
    cpu_headroom = max(0.0, settings.RESOURCE_HIGH_CPU_PERCENT - cpu_percent)
    memory_headroom = max(0.0, settings.RESOURCE_HIGH_MEMORY_PERCENT - memory_percent)
    cpu_slots = 1 + int(cpu_headroom // 20)
    memory_slots = 1 + int(memory_headroom // 12)
    core_slots = max(1, available_cpus // 3)
    target = max(1, min(ceiling, cpu_slots, memory_slots, core_slots))
    return AsrResourcePlan(
        target_concurrency=target,
        queue_capacity=target,
        pressure_level="normal",
        pause_new_tasks=False,
        message=f"资源状态正常，ASR 自适应并发为 {target}",
    )
