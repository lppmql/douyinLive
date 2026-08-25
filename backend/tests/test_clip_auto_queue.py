"""新离线终稿自动剪辑排队边界测试。"""

from types import SimpleNamespace

from app.services.clips import auto_queue


class _FakeQuery:
    def __init__(self, row):
        self._row = row

    def filter(self, *_args):
        return self

    def first(self):
        return self._row


class _FakeDb:
    def __init__(self):
        self.query_count = 0
        self.closed = False

    def query(self, _model):
        self.query_count += 1
        # 第一次代表真实流源存在；第二次代表没有待确认或已通过成片。
        return _FakeQuery((1,) if self.query_count == 1 else None)

    def close(self):
        self.closed = True


def test_new_offline_final_queues_clip_once(monkeypatch):
    fake_db = _FakeDb()
    queued_options = []
    monkeypatch.setattr(auto_queue.settings, "CLIP_AUTO_GENERATE", True)
    monkeypatch.setattr(auto_queue, "SessionLocal", lambda: fake_db)

    def enqueue(_module_key, options):
        queued_options.append(options)
        return SimpleNamespace(id=99), True

    monkeypatch.setattr(
        "app.services.tasks.control.collector_task_control.enqueue",
        enqueue,
    )

    assert auto_queue.queue_clip_after_offline_final(123, asr_task_id=456)
    assert queued_options == [
        {
            "session_id": 123,
            "trigger": "offline_final",
            "asr_task_id": 456,
        }
    ]
    assert fake_db.closed


def test_disabled_auto_clip_does_not_open_database(monkeypatch):
    monkeypatch.setattr(auto_queue.settings, "CLIP_AUTO_GENERATE", False)
    monkeypatch.setattr(
        auto_queue,
        "SessionLocal",
        lambda: (_ for _ in ()).throw(AssertionError("不应访问数据库")),
    )

    assert not auto_queue.queue_clip_after_offline_final(123)
