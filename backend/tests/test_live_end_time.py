import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.services.collector.end_live import process_live_end


class FakeQuery:
    def __init__(self, session):
        self.session = session

    def get(self, _session_id):
        return self.session

    def filter(self, *_args):
        return self

    def first(self):
        return SimpleNamespace(peak_online=0)

    def scalar(self):
        return 0

    def update(self, *_args, **_kwargs):
        return 0


class FakeDb:
    def __init__(self, session):
        self.session = session

    def query(self, *_args):
        return FakeQuery(self.session)

    def add(self, _item):
        pass

    def commit(self):
        pass


class LiveEndTimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_duration_never_becomes_negative(self):
        session = SimpleNamespace(
            id=1,
            live_start_time=datetime(2099, 1, 1),
            live_end_time=None,
            live_status="live",
            live_duration_seconds=0,
            peak_online_count=0,
            comments_count=0,
            leads_count=0,
        )

        with patch("app.services.collector.end_live.sync_session"):
            await process_live_end(FakeDb(session), 1)

        self.assertEqual(session.live_duration_seconds, 0)
        self.assertEqual(session.live_status, "ended")


if __name__ == "__main__":
    unittest.main()
