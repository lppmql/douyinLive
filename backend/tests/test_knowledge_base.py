import unittest
from types import SimpleNamespace

from pydantic import ValidationError

from app.api.v1.ai import QaRequest
from app.api.v1.knowledge_base import page_knowledge, page_time_slices
from app.models.knowledge_base import KnowledgeBase
from app.services.ai.kb_service import _contextual_question, _format_conversation, _normalize_history, _query_terms


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows
        self.offset_value = 0
        self.limit_value = len(rows)

    def count(self):
        return len(self.rows)

    def order_by(self, *_args):
        return self

    def offset(self, value):
        self.offset_value = value
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def all(self):
        return self.rows[self.offset_value:self.offset_value + self.limit_value]


class FakeDb:
    def __init__(self, rows):
        self.rows = rows

    def query(self, _model):
        return FakeQuery(self.rows)


class KnowledgeBaseTest(unittest.TestCase):
    def test_whole_knowledge_uses_server_pagination_shape(self):
        # 分页接口会读取 ORM 列，测试也使用真实模型，避免假的对象掩盖序列化契约。
        rows = [KnowledgeBase(id=1), KnowledgeBase(id=2)]

        result = page_knowledge(
            current=2,
            size=1,
            keyword=None,
            category=None,
            source_type=None,
            db=FakeDb(rows),
        )

        self.assertEqual(result["total"], 2)
        self.assertEqual(result["current"], 2)
        self.assertEqual([row["id"] for row in result["records"]], [2])

    def test_time_slice_page_serializes_real_metrics(self):
        row = SimpleNamespace(
            id=9,
            session_id=13249,
            anchor_name="大全谈开店天准",
            session_title="开店前听5分钟",
            slice_start_seconds=300,
            slice_end_seconds=600,
            slice_start_time=None,
            slice_end_time=None,
            transcript_text="真实话术",
            comments_text="真实评论",
            comment_count=3,
            high_intent_comment_count=1,
            unmapped_comment_count=0,
            metric_point_count=5,
            avg_online_count=8.6,
            peak_online_count=12,
            updated_at=None,
        )

        result = page_time_slices(
            current=1,
            size=8,
            keyword=None,
            anchor_name=None,
            evidence_type=None,
            db=FakeDb([row]),
        )

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["records"][0]["session_id"], 13249)
        self.assertEqual(result["records"][0]["avg_online_count"], 8.6)

    def test_chinese_question_produces_partial_search_terms(self):
        terms = _query_terms("丹姐最近直播的评论有什么问题？")
        self.assertIn("丹姐", terms)
        self.assertIn("评论", terms)
        self.assertTrue(any(term in terms for term in ("直播", "最近直播")))

    def test_english_and_number_terms_are_preserved(self):
        terms = _query_terms("分析 session 7302 ROI")
        self.assertIn("session", terms)
        self.assertIn("7302", terms)
        self.assertIn("roi", terms)

    def test_follow_up_question_reuses_recent_user_context(self):
        history = [
            {"role": "user", "content": "找出安徽地区有开店预算的高意向评论"},
            {"role": "assistant", "content": "找到场次11851和场次13251的两个相关时间片"},
        ]

        contextual = _contextual_question("分别来自哪些场次？", history)

        self.assertIn("安徽地区", contextual)
        self.assertIn("场次11851", contextual)
        self.assertIn("场次13251", contextual)
        self.assertIn("分别来自哪些场次", contextual)

    def test_history_is_bounded_and_formatted_by_role(self):
        history = [{"role": "user", "content": f"问题{i}"} for i in range(10)]
        normalized = _normalize_history(history)

        self.assertEqual(len(normalized), 8)
        self.assertNotIn("问题0", _format_conversation(history))
        self.assertIn("用户：问题9", _format_conversation(history))

    def test_qa_request_rejects_more_than_eight_history_messages(self):
        with self.assertRaises(ValidationError):
            QaRequest(
                question="继续追问",
                history=[{"role": "user", "content": f"问题{i}"} for i in range(9)],
            )


if __name__ == "__main__":
    unittest.main()
