from types import SimpleNamespace

from app.core.config import Settings
from app.services.asr.m3u8_pipe import M3u8Pipe
from app.services.tasks import runtime
from workers.asr_worker import build_chunk_ranges


def test_build_chunk_ranges_covers_real_duration_without_overlap():
    assert build_chunk_ranges(0, 300) == [(0.0, None)]
    assert build_chunk_ranges(601, 300) == [
        (0.0, 300.0),
        (300.0, 600.0),
        (600.0, 601.0),
    ]


def test_m3u8_pipe_adds_seek_and_duration_for_offline_chunk():
    pipe = M3u8Pipe(
        "https://example.invalid/real-playback.m3u8",
        {"Referer": "https://example.invalid/live"},
        start_seconds=300,
        duration_seconds=120,
    )
    command = pipe._build_cmd()

    assert command[command.index("-ss") + 1] == "300.000"
    assert command[command.index("-t") + 1] == "120.000"
    assert "https://example.invalid/real-playback.m3u8" in command


def test_synthetic_data_requires_all_explicit_switches():
    disabled = Settings(
        _env_file=None,
        DEBUG=True,
        ALLOW_SYNTHETIC_DATA=False,
        MONITOR_MOCK_MODE=True,
        ASR_ALLOW_MOCK=True,
    )
    enabled = Settings(
        _env_file=None,
        DEBUG=True,
        ALLOW_SYNTHETIC_DATA=True,
        MONITOR_MOCK_MODE=True,
        ASR_ALLOW_MOCK=True,
    )

    assert disabled.monitor_mock_enabled is False
    assert disabled.asr_mock_enabled is False
    assert enabled.monitor_mock_enabled is True
    assert enabled.asr_mock_enabled is True


def test_task_event_is_written_to_redis_stream(monkeypatch):
    calls = []

    class FakeRedis:
        @classmethod
        def from_url(cls, *_args, **_kwargs):
            return cls()

        def xadd(self, stream, payload, **options):
            calls.append((stream, payload, options))
            return "1-0"

        def close(self):
            return None

    monkeypatch.setattr(runtime, "Redis", FakeRedis)
    task = SimpleNamespace(
        id=12,
        status="running",
        trace_id="trace-12",
        worker_id="worker-1",
        retry_count=1,
    )

    event_id = runtime.publish_task_event("scraper", task, "progress", {"percent": 50})

    assert event_id == "1-0"
    assert calls[0][1]["trace_id"] == "trace-12"
    assert '"percent": 50' in calls[0][1]["details"]
