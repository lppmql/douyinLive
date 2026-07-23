from app.services.resources.asr_policy import build_asr_resource_plan


def _usage(cpu: float, memory: float, pressure: str) -> dict:
    return {
        "cpu_percent": cpu,
        "memory_percent": memory,
        "memory_total_bytes": 32 * 1024**3,
        "memory_used_bytes": int(32 * 1024**3 * memory / 100),
        "pressure_level": pressure,
    }


def test_asr_uses_more_than_one_worker_when_computer_has_headroom():
    plan = build_asr_resource_plan(
        _usage(cpu=18, memory=42, pressure="normal"),
        cpu_count=12,
        max_concurrency=4,
    )

    assert plan.target_concurrency > 1
    assert plan.queue_capacity == plan.target_concurrency
    assert plan.pause_new_tasks is False


def test_asr_reduces_to_one_worker_under_high_pressure():
    plan = build_asr_resource_plan(
        _usage(cpu=87, memory=81, pressure="high"),
        cpu_count=12,
        max_concurrency=4,
    )

    assert plan.target_concurrency == 1
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
