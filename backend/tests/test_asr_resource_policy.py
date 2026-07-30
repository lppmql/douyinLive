from app.services.resources.asr_policy import build_asr_resource_plan


def _usage(cpu: float, memory: float, pressure: str) -> dict:
    return {
        "cpu_percent": cpu,
        "memory_percent": memory,
        "memory_total_bytes": 32 * 1024**3,
        "memory_used_bytes": int(32 * 1024**3 * memory / 100),
        "pressure_level": pressure,
    }


def test_asr_keeps_single_funasr_connection_when_computer_has_headroom():
    plan = build_asr_resource_plan(
        _usage(cpu=18, memory=42, pressure="normal"),
        cpu_count=12,
        max_concurrency=4,
    )

    # 两个逻辑任务可以同时等待，但底层 FunASR 仍由连接锁严格串行。
    assert plan.target_concurrency == 2
    assert plan.queue_capacity == 2
    assert plan.pause_new_tasks is False


def test_asr_keeps_two_logical_lanes_under_high_pressure():
    plan = build_asr_resource_plan(
        _usage(cpu=87, memory=81, pressure="high"),
        cpu_count=12,
        max_concurrency=4,
    )

    assert plan.target_concurrency == 2
    assert plan.queue_capacity == 2
    assert plan.pause_new_tasks is False


def test_asr_pauses_new_work_under_critical_memory_pressure():
    plan = build_asr_resource_plan(
        _usage(cpu=60, memory=96, pressure="critical"),
        cpu_count=12,
        max_concurrency=4,
    )

    assert plan.target_concurrency == 0
    assert plan.queue_capacity == 0
    assert plan.pause_new_tasks is True
