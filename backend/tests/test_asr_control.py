from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.api.v1.ws import build_full_transcript_text, get_full_text, serialize_transcription_task
from app.services.asr import control
from app.services.asr.control import _worker_pids


def test_worker_pids_excludes_pgrep_and_shell_commands():
    process_table = """
  101 /usr/bin/python3 /project/.venv/bin/python -m workers.asr_worker
  105 /project/.venv/ /project/.venv/bin/python -m workers.asr_worker
  102 /bin/zsh /bin/zsh -c pgrep -f 'python -m workers.asr_worker'
  103 /usr/bin/pgrep pgrep -f python -m workers.asr_worker
  104 /usr/bin/python3 /project/.venv/bin/python -m app.main
"""

    with patch("app.services.asr.control.subprocess.run") as run:
        run.return_value.stdout = process_table
        assert _worker_pids() == [101, 105]
        run.assert_called_once_with(
            ["ps", "-axo", "pid=,comm=,args="],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )


def test_runtime_status_requires_fresh_worker_heartbeat(tmp_path, monkeypatch):
    heartbeat_path = tmp_path / "asr-worker.json"
    clock = [1000.0]
    monkeypatch.setattr(control, "ASR_RUNTIME_STATE_PATH", heartbeat_path)
    monkeypatch.setattr(control.os, "getpid", lambda: 321)
    monkeypatch.setattr(control.time, "time", lambda: clock[0])
    monkeypatch.setattr(control, "_worker_pids", lambda: [321])
    monkeypatch.setattr(control, "_engine_running", lambda: True)

    control.write_asr_worker_heartbeat("asr:test:321")
    healthy = control.get_asr_runtime_status()
    assert healthy["enabled"] is True
    assert healthy["worker_healthy"] is True
    assert healthy["worker_status"] == "healthy"

    clock[0] += control.ASR_WORKER_HEARTBEAT_TIMEOUT_SECONDS + 1
    stale = control.get_asr_runtime_status()
    assert stale["enabled"] is False
    assert stale["worker_running"] is True
    assert stale["worker_healthy"] is False
    assert stale["worker_status"] == "stale"


def test_terminate_worker_force_kills_process_that_ignores_sigterm(monkeypatch):
    worker_snapshots = iter(([456], [456], []))
    signals = []
    monkeypatch.setattr(control, "_worker_pids", lambda: next(worker_snapshots))
    monkeypatch.setattr(control.os, "kill", lambda pid, sig: signals.append((pid, sig)))
    monkeypatch.setattr(control, "clear_asr_worker_heartbeat", lambda: None)

    forced = control._terminate_worker_processes(grace_seconds=0)

    assert forced == [456]
    assert signals == [(456, control.signal.SIGTERM), (456, control.signal.SIGKILL)]


def test_transcription_task_payload_keeps_real_failure_context():
    now = datetime(2026, 7, 15, 20, 30)
    task = SimpleNamespace(
        id=52,
        session_id=13238,
        status="failed",
        task_type="offline",
        error_message="真实回放地址已失效",
        retry_count=2,
        max_retries=3,
        started_at=now,
        completed_at=now,
        created_at=now,
        updated_at=now,
    )
    session = SimpleNamespace(
        anchor_name="零食避坑听我说",
        session_title="开店前听5分钟",
        live_start_time=now,
        live_duration_seconds=4568,
    )

    result = serialize_transcription_task(task, session, 18)

    assert result["session_id"] == 13238
    assert result["anchor_name"] == "零食避坑听我说"
    assert result["error_message"] == "真实回放地址已失效"
    assert result["segment_count"] == 18
    assert result["retry_count"] == 2


def test_missing_full_transcript_is_a_normal_empty_state():
    class EmptyQuery:
        def filter(self, *_args):
            return self

        def first(self):
            return None

        def order_by(self, *_args):
            return self

        def limit(self, _limit):
            return self

        def all(self):
            return []

    db = SimpleNamespace(query=lambda _model: EmptyQuery())

    result = get_full_text(13246, db=db)

    assert result == {"id": None, "full_text": "", "available": False}


def test_full_transcript_falls_back_to_real_segments():
    segments = [
        SimpleNamespace(segment_start=12.3, text_content="开零食店先核算预算"),
        SimpleNamespace(segment_start=18.8, text_content="资料可以通过站内私信领取"),
    ]

    text = build_full_transcript_text(segments)

    assert text == "[12.3s] 开零食店先核算预算\n[18.8s] 资料可以通过站内私信领取"
