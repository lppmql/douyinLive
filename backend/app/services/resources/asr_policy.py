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
            # 两个只是等待单模型的逻辑任务，真正推理始终单连接；高压力时仍需
            # 让协调器同时看见直播和终稿，否则 3:1 会退化为直播永久独占。
            target_concurrency=2,
            queue_capacity=2,
            pressure_level="high",
            pause_new_tasks=False,
            message="电脑资源偏高，ASR 保留双逻辑队列并继续单模型串行",
        )

    # 同时保留一个直播任务和一个最新下播终稿任务。它们只是两个逻辑任务，
    # 真正进入 FunASR 时仍由 AsrLaneCoordinator 严格串行，不会加载第二份模型。
    return AsrResourcePlan(
        target_concurrency=2,
        queue_capacity=2,
        pressure_level="normal",
        pause_new_tasks=False,
        message="资源状态正常，ASR 按直播三片、最新终稿一片智能分时",
    )
