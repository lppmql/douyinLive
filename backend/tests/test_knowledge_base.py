import unittest

from app.services.ai.kb_service import _query_terms


class KnowledgeBaseTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
