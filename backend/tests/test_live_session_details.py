import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.api.v1.live_sessions import _is_allowed_avatar_url, get_session_avatar, get_session_details
from app.models.comments import Comment
from app.models.live_audience_profiles import LiveAudienceProfile
from app.models.live_metrics import LiveMetric
from app.models.live_sessions import LiveSession
from app.models.stream_sources import StreamSource
from app.schemas import LiveAudienceProfileResponse


class ProfileRow:
    dimension_type = "age"
    dimension_name = "31-40"
    ratio = 44
    count = 0


class LiveSessionDetailsTest(unittest.TestCase):
    def test_avatar_proxy_only_allows_douyin_image_hosts(self):
        self.assertTrue(_is_allowed_avatar_url("https://p3.douyinpic.com/avatar.webp"))
        self.assertFalse(_is_allowed_avatar_url("http://p3.douyinpic.com/avatar.webp"))
        self.assertFalse(_is_allowed_avatar_url("https://douyinpic.com.example.test/avatar.webp"))

    def test_avatar_proxy_returns_real_image_bytes(self):
        session = SimpleNamespace(anchor_avatar_url="https://p3.douyinpic.com/avatar.webp")
        upstream = SimpleNamespace(
            content=b"real-webp-bytes",
            headers={"content-type": "image/webp"},
            raise_for_status=lambda: None,
        )

        with patch("app.api.v1.live_sessions.httpx.get", return_value=upstream):
            response = get_session_avatar(9, db=SimpleNamespace(get=lambda *_args: session))

        self.assertEqual(response.media_type, "image/webp")
        self.assertEqual(response.body, b"real-webp-bytes")

    def test_profile_response_accepts_orm_rows(self):
        profile = LiveAudienceProfileResponse.model_validate(ProfileRow())
        self.assertEqual(profile.dimension_type, "age")
        self.assertEqual(profile.ratio, 44)

    def test_detail_endpoint_keeps_assets_after_video_route_addition(self):
        session = SimpleNamespace(stream_url="https://example.test/fallback.m3u8")
        stream = SimpleNamespace(m3u8_url="https://example.test/live.m3u8", status="active")
        db = DetailDb(session, stream)
        session_data = {
            "id": 9,
            "room_id": 1,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        with patch("app.api.v1.live_sessions._attach_room_profile", return_value=session_data):
            detail = get_session_details(9, db=db)

        self.assertEqual(detail.stream_url, stream.m3u8_url)
        self.assertEqual(detail.stream_source_count, 1)
        self.assertEqual(detail.comments, [])


class DetailQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def limit(self, _limit):
        return self

    def all(self):
        return self.rows


class DetailDb:
    def __init__(self, session, stream):
        self.session = session
        self.stream = stream

    def get(self, model, _record_id):
        return self.session if model is LiveSession else None

    def query(self, model):
        rows = {
            LiveMetric: [],
            Comment: [],
            StreamSource: [self.stream],
            LiveAudienceProfile: [],
        }[model]
        return DetailQuery(rows)


if __name__ == "__main__":
    unittest.main()
