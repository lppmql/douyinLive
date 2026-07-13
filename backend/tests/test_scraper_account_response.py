import unittest
from datetime import datetime

from app.models.scraper_accounts import ScraperAccount
from app.schemas.scraper import ScraperAccountResponse, ScraperTaskResponse
from app.models.scraper_tasks import ScraperTask


class ScraperAccountResponseTest(unittest.TestCase):
    def test_exposes_saved_flags_without_sensitive_state(self):
        now = datetime.utcnow()
        account = ScraperAccount(
            id=5,
            account_name="collector",
            login_status="logged_in",
            storage_state_path="/private/login.json",
            cookies_json='[{"name":"session","value":"secret"}]',
            browser_fingerprint_json='{"user_agent":"secret"}',
            created_at=now,
            updated_at=now,
        )

        payload = ScraperAccountResponse.model_validate(account).model_dump()

        self.assertTrue(payload["cookie_saved"])
        self.assertTrue(payload["fingerprint_saved"])
        self.assertNotIn("cookies_json", payload)
        self.assertNotIn("browser_fingerprint_json", payload)
        self.assertNotIn("storage_state_path", payload)

    def test_task_response_contains_real_progress_fields(self):
        now = datetime.utcnow()
        task = ScraperTask(
            id=12,
            task_type="collect_all",
            status="running",
            progress_percent=60,
            progress_current=8,
            progress_total=10,
            progress_stage="enterprise_sync",
            progress_message="正在同步企业主播",
            created_at=now,
            updated_at=now,
        )

        payload = ScraperTaskResponse.model_validate(task).model_dump()

        self.assertEqual(payload["progress_percent"], 60)
        self.assertEqual(payload["progress_current"], 8)
        self.assertEqual(payload["progress_total"], 10)
        self.assertEqual(payload["progress_stage"], "enterprise_sync")


if __name__ == "__main__":
    unittest.main()
