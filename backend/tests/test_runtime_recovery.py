import unittest
from unittest.mock import patch

from app.main import recover_interrupted_collector_tasks


class FakeTask:
    def __init__(self):
        self.status = "running"
        self.completed_at = None
        self.error_message = None
        self.progress_stage = None
        self.progress_message = None


class FakeQuery:
    def __init__(self, tasks):
        self.tasks = tasks

    def filter(self, *_args):
        return self

    def all(self):
        return self.tasks


class FakeSession:
    def __init__(self, tasks):
        self.tasks = tasks
        self.committed = False
        self.closed = False

    def query(self, *_args):
        return FakeQuery(self.tasks)

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


class RuntimeRecoveryTest(unittest.TestCase):
    def test_marks_interrupted_collector_tasks_failed(self):
        task = FakeTask()
        session = FakeSession([task])

        with patch("app.main.SessionLocal", return_value=session):
            recovered = recover_interrupted_collector_tasks()

        self.assertEqual(recovered, 1)
        self.assertEqual(task.status, "failed")
        self.assertEqual(task.progress_stage, "interrupted")
        self.assertIsNotNone(task.completed_at)
        self.assertTrue(session.committed)
        self.assertTrue(session.closed)


if __name__ == "__main__":
    unittest.main()
