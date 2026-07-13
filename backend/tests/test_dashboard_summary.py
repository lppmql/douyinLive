import unittest
from types import SimpleNamespace

from app.api.v1.dashboard import _serialize_summary


class DashboardSummaryTest(unittest.TestCase):
    def test_calculates_real_completion_rate_and_lead_cost(self):
        row = SimpleNamespace(
            anchor_count=8,
            session_count=25,
            live_session_count=1,
            detail_complete_count=20,
            total_viewers=1000,
            total_comments=200,
            total_leads=10,
            total_ad_cost=125.5,
        )

        result = _serialize_summary(row)

        self.assertEqual(result["detail_completion_rate"], 80.0)
        self.assertEqual(result["average_lead_cost"], 12.55)

    def test_handles_empty_database_without_division_by_zero(self):
        row = SimpleNamespace(
            anchor_count=0,
            session_count=0,
            live_session_count=0,
            detail_complete_count=0,
            total_viewers=0,
            total_comments=0,
            total_leads=0,
            total_ad_cost=0,
        )

        result = _serialize_summary(row)

        self.assertEqual(result["detail_completion_rate"], 0)
        self.assertEqual(result["average_lead_cost"], 0)
