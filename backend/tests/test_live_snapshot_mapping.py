import unittest
from types import SimpleNamespace

from app.services.collector.manual_collect import (
    _apply_overview_to_session,
    _parse_watch_profiles,
)


class LiveSnapshotMappingTest(unittest.TestCase):
    def test_maps_real_overview_metrics_to_live_session(self):
        session = SimpleNamespace(
            total_viewers=0,
            realtime_online_count=0,
            like_count=0,
            comments_count=0,
            leads_count=0,
            scene_leads_count=0,
            avg_online_count=0,
            peak_online_count=0,
            viewed_count=0,
            private_message_count=0,
            private_message_longterm_count=0,
            mini_windmill_click_count=0,
            card_click_count=0,
            new_followers=0,
            share_count=0,
            share_users=0,
            like_users=0,
            comment_users=0,
            interaction_count=0,
            interaction_users=0,
            watch_count=0,
            watch_over_1m_count=0,
            fans_club_join_count=0,
            gift_count=0,
            dislike_count=0,
            dislike_users=0,
            wechat_add_count=0,
            form_submit_count=0,
            form_submit_users=0,
            avg_watch_seconds=0.0,
            fans_avg_watch_seconds=0.0,
            ad_cost=0.0,
            exposure_enter_rate=0.0,
            fans_view_ratio=0.0,
            scene_lead_conversion_rate=0.0,
            mini_windmill_click_rate=0.0,
            card_click_rate=0.0,
            follow_rate=0.0,
            comment_rate=0.0,
            interaction_rate=0.0,
            share_rate=0.0,
            like_rate=0.0,
            fans_club_join_rate=0.0,
            gift_amount=0.0,
            wechat_add_cost=0.0,
            form_submit_cost=0.0,
            live_end_time=None,
            live_status="live",
        )
        row = {"metrics": {
            "lp_screen_live_watch_uv": "1234",
            "lp_screen_live_user_realtime": "56",
            "lp_screen_live_like_count": "789",
            "lp_screen_live_comment_count": "32",
            "lp_screen_clue_uv": "4",
        }}

        changed = _apply_overview_to_session(session, row)

        self.assertTrue(changed)
        self.assertEqual(session.total_viewers, 1234)
        self.assertEqual(session.realtime_online_count, 56)
        self.assertEqual(session.like_count, 789)
        self.assertEqual(session.comments_count, 32)
        self.assertEqual(session.leads_count, 4)

    def test_parses_real_watch_profile_json_fields(self):
        rows = [{"fields": {
            "lp_screen_live_watch_profile_gender": '{"female":22,"male":78}',
            "lp_screen_live_watch_profile_region": '{"华东":35,"华中":23}',
        }}]

        profiles = _parse_watch_profiles(rows)

        self.assertEqual(len(profiles), 4)
        self.assertIn(
            {"dimension_type": "gender", "dimension_name": "male", "ratio": 78.0, "count": 0},
            profiles,
        )
