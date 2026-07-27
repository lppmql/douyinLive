"""根据电脑实时资源为 ASR 计算并发和排队容量。"""

from __future__ import annotations

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

    # 当前 FunASR C++ 服务端实测只支持一条稳定 WebSocket。即使电脑资源富余，
    # 同时启动第二个识别任务也可能让容器崩溃，因此任务层固定单并发。
    # CPU 和内存策略仍负责在严重压力时暂停新分片。
    return AsrResourcePlan(
        target_concurrency=1,
        queue_capacity=1,
        pressure_level="normal",
        pause_new_tasks=False,
        message="资源状态正常，FunASR 按稳定单连接运行",
    )
