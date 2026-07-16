from types import SimpleNamespace

from app.models.analysis_reports import AnalysisReport
from app.models.live_sessions import LiveSession
from app.models.transcript_segments import TranscriptSegment
from app.services.ai import post_collection
from app.services.ai.kb_service import save_analysis_to_kb


class FakeQuery:
    def __init__(self, count_value: int):
        self.count_value = count_value

    def filter(self, *_args):
        return self

    def count(self):
        return self.count_value

    def order_by(self, *_args):
        return self

    def first(self):
        return None


class FakeDb:
    def __init__(self):
        self.rollback_count = 0

    def get(self, model, _session_id):
        if model is LiveSession:
            return SimpleNamespace(id=13254)
        return None

    def query(self, model):
        if model is TranscriptSegment:
            return FakeQuery(12)
        if model is AnalysisReport:
            return FakeQuery(1)
        return FakeQuery(0)

    def rollback(self):
        self.rollback_count += 1


def test_post_collection_pipeline_runs_review_before_knowledge(monkeypatch):
    calls = []
    db = FakeDb()
    monkeypatch.setattr(post_collection, "score_session_transcript", lambda *_args: {"total_score": 86})
    monkeypatch.setattr(post_collection, "generate_findings", lambda *_args: calls.append("review") or [1, 2])
    monkeypatch.setattr(
        post_collection,
        "sync_session_to_kb",
        lambda *_args: calls.append("knowledge") or {"transcript_saved": 1, "review_saved": 1},
    )
    monkeypatch.setattr(post_collection, "sync_session", lambda *_args: calls.append("dataease"))

    result = post_collection.process_session_post_collection(db, 13254)

    assert result["success"] is True
    assert result["transcript_count"] == 12
    assert result["speech_score"] == 86
    assert result["review_finding_count"] == 2
    assert calls == ["review", "knowledge", "dataease"]


def test_post_collection_pipeline_keeps_knowledge_stage_after_review_failure(monkeypatch):
    calls = []
    db = FakeDb()
    monkeypatch.setattr(post_collection, "score_session_transcript", lambda *_args: None)

    def fail_review(*_args):
        raise RuntimeError("真实复盘生成失败")

    monkeypatch.setattr(post_collection, "generate_findings", fail_review)
    monkeypatch.setattr(
        post_collection,
        "sync_session_to_kb",
        lambda *_args: calls.append("knowledge") or {"transcript_saved": 1},
    )
    monkeypatch.setattr(post_collection, "sync_session", lambda *_args: calls.append("dataease"))

    result = post_collection.process_session_post_collection(db, 13254)

    assert result["success"] is False
    assert result["errors"]["review"] == "真实复盘生成失败"
    assert calls == ["knowledge", "dataease"]
    assert db.rollback_count == 1


def test_existing_ai_knowledge_is_updated_when_report_changes():
    report = SimpleNamespace(
        report_title="话术评分 - 场次13254",
        report_content={"total_score": 88},
        summary="88",
    )
    existing = SimpleNamespace(
        title="话术评分 - 场次13254",
        content='{"total_score": 70}',
        category="分析结论",
    )

    class Rows:
        def __init__(self, rows):
            self.rows = rows

        def filter(self, *_args):
            return self

        def all(self):
            return self.rows

        def first(self):
            return self.rows[0] if self.rows else None

    class KnowledgeDb:
        def __init__(self):
            self.query_count = 0
            self.commit_count = 0

        def query(self, _model):
            self.query_count += 1
            return Rows([report] if self.query_count == 1 else [existing])

        def commit(self):
            self.commit_count += 1

    db = KnowledgeDb()
    changed = save_analysis_to_kb(db, 13254)

    assert changed == 1
    assert '"total_score": 88' in existing.content
    assert db.commit_count == 1
