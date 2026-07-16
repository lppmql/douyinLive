from app.api.v1.collector import clear_logs
from app.models.scraper_logs import ScraperLog


class FakeLogQuery:
    def __init__(self, deleted_count: int):
        self.deleted_count = deleted_count

    def delete(self, synchronize_session: bool):
        assert synchronize_session is False
        return self.deleted_count


class FakeDb:
    def __init__(self, deleted_count: int):
        self.deleted_count = deleted_count
        self.committed = False
        self.rolled_back = False

    def query(self, model):
        assert model is ScraperLog
        return FakeLogQuery(self.deleted_count)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def test_clear_logs_deletes_only_log_rows_and_commits():
    db = FakeDb(deleted_count=27)

    result = clear_logs(db=db)

    assert result == {"message": "采集日志已清空", "deleted_count": 27}
    assert db.committed is True
    assert db.rolled_back is False
