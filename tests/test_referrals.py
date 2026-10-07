import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from database import database


class ReferralAndBonusTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.db_name_patch = patch.object(database, "DB_NAME", str(self.db_path))
        self.db_name_patch.start()
        database.create_database()

    def tearDown(self):
        self.db_name_patch.stop()
        self.temp_dir.cleanup()

    def test_referral_awards_referrer_once_after_first_success(self):
        database.register_user(101, "inviter", "Inviter")
        self.assertTrue(database.register_user(202, "friend", "Friend"))
        self.assertTrue(database.claim_referral(202, 101))
        self.assertFalse(database.claim_referral(202, 101))

        database.add_history(202, "https://example.com/video", "video")
        database.increase_download_count(202)
        database.increase_download_count(202)

        invited, qualified, inviter_bonus = database.get_referral_stats(101)
        self.assertEqual((invited, qualified, inviter_bonus), (1, 1, 5))

    def test_bonus_is_used_after_daily_allowance(self):
        database.register_user(303, "user", "User")
        with database.connect() as conn:
            conn.execute(
                "UPDATE users SET downloads_today = 20, last_download_date = ? WHERE telegram_id = ?",
                (date.today().isoformat(), 303),
            )
            conn.execute(
                "UPDATE users SET bonus_downloads_remaining = 1 WHERE telegram_id = ?",
                (303,),
            )

        self.assertTrue(database.can_download(303))
        database.increase_download_count(303)
        self.assertFalse(database.can_download(303))
        profile = database.get_user_profile(303)
        self.assertEqual(profile[7], 0)

    def test_self_referral_is_rejected(self):
        database.register_user(404, "user", "User")
        self.assertFalse(database.claim_referral(404, 404))


if __name__ == "__main__":
    unittest.main()
