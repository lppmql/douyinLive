from unittest.mock import patch

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
