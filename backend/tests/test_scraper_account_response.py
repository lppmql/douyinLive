import unittest
from datetime import datetime

from app.models.scraper_accounts import ScraperAccount
from app.schemas.scraper import ScraperAccountResponse


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


if __name__ == "__main__":
    unittest.main()
