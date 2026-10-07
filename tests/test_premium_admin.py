import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from database import database


class AdminPremiumTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(database, "DB_NAME", str(Path(self.temp_dir.name) / "test.db"))
        self.db_patch.start()
        database.create_database()
        database.register_user(901, "premium_user", "Premium User")

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_admin_grant_extension_and_revoke_are_audited(self):
        first = database.update_user_premium(901, 30, 700)
        self.assertTrue(first["is_premium"])
        first_expiry = datetime.fromisoformat(first["premium_until"])
        self.assertGreater(first_expiry, datetime.now() + timedelta(days=29))

        second = database.update_user_premium(901, 7, 700)
        second_expiry = datetime.fromisoformat(second["premium_until"])
        self.assertEqual(second_expiry.date(), (first_expiry + timedelta(days=7)).date())

        revoked = database.update_user_premium(901, None, 700)
        self.assertFalse(revoked["is_premium"])
        self.assertIsNone(database.get_user_profile(901)[3])
        with database.connect() as conn:
            actions = [row[0] for row in conn.execute(
                "SELECT action FROM security_log WHERE telegram_id = 901 ORDER BY id"
            ).fetchall()]
        self.assertEqual(actions, ["PREMIUM_GRANTED", "PREMIUM_GRANTED", "PREMIUM_REVOKED"])

    def test_expired_premium_is_revoked_before_download_limit_check(self):
        with database.connect() as conn:
            conn.execute(
                "UPDATE users SET is_premium = 1, premium_until = ?, downloads_today = 20, last_download_date = ? WHERE telegram_id = 901",
                (
                    (datetime.now() - timedelta(days=1)).isoformat(sep=" "),
                    date.today().isoformat(),
                ),
            )

        self.assertFalse(database.can_download(901))
        profile = database.get_user_profile(901)
        self.assertEqual(profile[2], 0)
        self.assertIsNone(profile[3])

    def test_expiry_preview_extends_an_active_subscription(self):
        database.update_user_premium(901, 30, 700)
        current = datetime.fromisoformat(database.get_user_profile(901)[3])
        preview = datetime.fromisoformat(database.preview_premium_expiry(901, 7))
        self.assertEqual(preview.date(), (current + timedelta(days=7)).date())


if __name__ == "__main__":
    unittest.main()
