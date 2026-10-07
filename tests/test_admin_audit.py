import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database import database


class AdminAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(database, "DB_NAME", str(Path(self.temp_dir.name) / "test.db"))
        self.db_patch.start()
        database.create_database()
        database.register_user(901, "target_user", "Target")

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_account_changes_are_audited_and_filterable_by_target(self):
        database.ban_user(901, 700, "Спам")
        database.unban_user(901, 701)
        database.add_bot_admin(901, 702)
        database.remove_bot_admin(901, 703)

        rows, total = database.get_admin_audit_page(user_id=901)
        self.assertEqual(total, 4)
        self.assertEqual([row[3] for row in rows], [
            "ADMIN_REMOVED", "ADMIN_ADDED", "USER_UNBANNED", "USER_BANNED"
        ])
        self.assertEqual([row[5] for row in rows], [703, 702, 701, 700])
        self.assertEqual(database.get_admin_audit_page(user_id=999)[1], 0)

    def test_hiding_user_preserves_profile_and_can_be_reversed(self):
        database.add_history(901, "https://instagram.com/p/example", "Instagram видео")

        self.assertTrue(database.set_user_hidden(901, True, 700))
        self.assertNotIn(901, [row[0] for row in database.get_recent_users(20)])
        self.assertEqual(database.get_hidden_users(20)[0][0], 901)
        self.assertTrue(database.is_user_hidden(901))
        self.assertEqual(database.get_user_profile(901)[0], "Target")
        self.assertEqual(len(database.get_history(901)), 1)

        self.assertTrue(database.set_user_hidden(901, False, 700))
        self.assertIn(901, [row[0] for row in database.get_recent_users(20)])
        self.assertFalse(database.is_user_hidden(901))


if __name__ == "__main__":
    unittest.main()
