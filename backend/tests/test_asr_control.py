from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.api.v1.ws import get_full_text, serialize_transcription_task
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
            check=False,
        )


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

    db = SimpleNamespace(query=lambda _model: EmptyQuery())

    result = get_full_text(13246, db=db)

    assert result == {"id": None, "full_text": "", "available": False}
