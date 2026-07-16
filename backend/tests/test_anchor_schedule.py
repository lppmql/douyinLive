import unittest
from datetime import date, datetime, time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.anchor_schedules import AnchorSchedule
from app.models.base import Base
from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.services.schedule_service import build_schedule_dashboard, build_schedule_range_dashboard


class AnchorScheduleTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            engine,
            tables=[LiveRoom.__table__, LiveSession.__table__, AnchorSchedule.__table__],
        )
        self.db = sessionmaker(bind=engine)()
        self.room = LiveRoom(account_name="account", anchor_name="文豪", platform="douyin", status=True)
        self.db.add(self.room)
        self.db.flush()
        self.schedule = AnchorSchedule(
            source_anchor_name="刘文豪",
            display_name="刘文豪（文豪）",
            match_keywords=["刘文豪", "文豪"],
            room_name="2号直播间",
            network_name="家庭宽带1",
            session_index=1,
            planned_start_time=time(9, 50),
            planned_end_time=time(11, 10),
            expected_duration_minutes=80,
            active=True,
            source_name="排班.xls",
        )
        self.db.add(self.schedule)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def add_session(self, start: datetime, duration_seconds: int, status: str = "ended"):
        session = LiveSession(
            room_id=self.room.id,
            anchor_name="文豪聊零食店天准",
            live_start_time=start,
            live_end_time=start if status == "live" else start.replace(hour=11, minute=10),
            live_duration_seconds=duration_seconds,
            live_status=status,
        )
        self.db.add(session)
        self.db.commit()
        return session

    def test_exact_80_minutes_is_compliant(self):
        self.add_session(datetime(2026, 7, 16, 9, 52), 80 * 60)

        result = build_schedule_dashboard(self.db, date(2026, 7, 16), datetime(2026, 7, 16, 12, 0))

        self.assertEqual(result["summary"]["matched_count"], 1)
        self.assertEqual(result["summary"]["duration_compliant_count"], 1)
        self.assertEqual(result["summary"]["cross_hour_count"], 0)
        self.assertEqual(result["rows"][0]["status"], "completed")

    def test_short_duration_and_late_cross_hour_are_both_reminded(self):
        self.add_session(datetime(2026, 7, 16, 10, 1), 70 * 60)

        result = build_schedule_dashboard(self.db, date(2026, 7, 16), datetime(2026, 7, 16, 12, 0))

        self.assertEqual(result["rows"][0]["status"], "duration_short")
        self.assertEqual({item["type"] for item in result["reminders"]}, {"duration", "cross_hour"})

    def test_early_cross_hour_is_reminded(self):
        self.add_session(datetime(2026, 7, 16, 8, 59), 80 * 60)

        result = build_schedule_dashboard(self.db, date(2026, 7, 16), datetime(2026, 7, 16, 12, 0))

        self.assertEqual(result["rows"][0]["status"], "completed")
        self.assertEqual(result["summary"]["cross_hour_count"], 1)
        self.assertEqual([item["type"] for item in result["reminders"]], ["cross_hour"])

    def test_early_start_within_planned_hour_is_not_cross_hour(self):
        self.add_session(datetime(2026, 7, 16, 9, 1), 80 * 60)

        result = build_schedule_dashboard(self.db, date(2026, 7, 16), datetime(2026, 7, 16, 12, 0))

        self.assertEqual(result["summary"]["cross_hour_count"], 0)
        self.assertEqual(result["reminders"], [])

    def test_future_slot_is_not_reported_missing(self):
        result = build_schedule_dashboard(self.db, date(2026, 7, 16), datetime(2026, 7, 16, 9, 55))

        self.assertEqual(result["rows"][0]["status"], "upcoming")
        self.assertEqual(result["summary"]["missing_count"], 0)

    def test_slot_is_missing_after_next_whole_hour(self):
        result = build_schedule_dashboard(self.db, date(2026, 7, 16), datetime(2026, 7, 16, 10, 1))

        self.assertEqual(result["rows"][0]["status"], "missing")
        self.assertEqual(result["summary"]["missing_count"], 1)
        self.assertEqual(result["anchors"][0]["missing_count"], 1)
        self.assertEqual(
            result["anchors"][0]["missing_by_date"],
            [{"schedule_date": "2026-07-16", "count": 1, "session_indexes": [1]}],
        )

    def test_date_range_aggregates_each_day_and_keeps_row_dates(self):
        self.add_session(datetime(2026, 7, 16, 9, 52), 80 * 60)

        result = build_schedule_range_dashboard(
            self.db,
            date(2026, 7, 16),
            date(2026, 7, 17),
            datetime(2026, 7, 17, 12, 0),
        )

        self.assertEqual(result["day_count"], 2)
        self.assertEqual(result["summary"]["planned_count"], 2)
        self.assertEqual(result["summary"]["matched_count"], 1)
        self.assertEqual(result["summary"]["missing_count"], 1)
        self.assertEqual(result["anchors"][0]["expected_count"], 2)
        self.assertEqual(result["anchors"][0]["missing_count"], 1)
        self.assertEqual(
            result["anchors"][0]["missing_by_date"],
            [{"schedule_date": "2026-07-17", "count": 1, "session_indexes": [1]}],
        )
        self.assertEqual([row["schedule_date"] for row in result["rows"]], ["2026-07-16", "2026-07-17"])

    def test_date_range_rejects_invalid_or_oversized_ranges(self):
        with self.assertRaisesRegex(ValueError, "结束日期"):
            build_schedule_range_dashboard(self.db, date(2026, 7, 17), date(2026, 7, 16))
        with self.assertRaisesRegex(ValueError, "最多支持 31 天"):
            build_schedule_range_dashboard(self.db, date(2026, 7, 1), date(2026, 8, 1))


if __name__ == "__main__":
    unittest.main()
