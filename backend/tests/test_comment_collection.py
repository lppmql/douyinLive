import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.collector.room import _fetch_all_session_comments
from app.services.collector.utils import (
    _comment_belongs_to_session,
    _comment_identity,
)


class CommentCollectionTest(unittest.IsolatedAsyncioTestCase):
    def test_rejects_comment_outside_live_session(self):
        start = datetime(2026, 7, 13, 18, 0)
        end = start + timedelta(hours=1)
        self.assertTrue(_comment_belongs_to_session(start + timedelta(minutes=30), start, end))
        self.assertFalse(_comment_belongs_to_session(start - timedelta(hours=1), start, end))
        self.assertFalse(_comment_belongs_to_session(start + timedelta(hours=2), start, end))

    def test_identity_keeps_same_content_from_different_users(self):
        when = datetime(2026, 7, 13, 20, 0, 0)
        first = _comment_identity("用户甲", "多少钱", when, "sec-a")
        second = _comment_identity("用户乙", "多少钱", when, "sec-b")
        self.assertNotEqual(first, second)

    async def test_comment_api_result_is_authoritative(self):
        response = {
            "data": {
                "total": "1",
                "comments": [{
                    "nickName": "用户甲",
                    "secUId": "sec-a",
                    "webcastUid": "webcast-a",
                    "content": "想了解加盟",
                    "createTime": "1783940000",
                }],
            }
        }
        with patch(
            "app.services.collector.room._fetch_enterprise_post",
            new=AsyncMock(return_value=response),
        ):
            comments, authoritative = await _fetch_all_session_comments(object(), "room-1")

        self.assertTrue(authoritative)
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["user_sec_uid"], "sec-a")


if __name__ == "__main__":
    unittest.main()
