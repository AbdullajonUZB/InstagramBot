import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database import database


class AdminDownloadJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(database, "DB_NAME", str(Path(self.temp_dir.name) / "test.db"))
        self.db_patch.start()
        database.create_database()
        database.register_user(1001, "alice_test", "Alice")
        database.register_user(1002, "bob_test", "Bob")

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_journal_filters_successful_records_by_service_and_user(self):
        database.add_history(1001, "https://instagram.com/p/one", "Instagram фото")
        database.add_history(1002, "https://youtube.com/watch?v=two", "YouTube видео")
        database.add_download(1001, "alice_test", "Alice", "https://example.com/fail", "Instagram видео", "failed")

        rows, total = database.get_admin_downloads_page(service="instagram", user_id=1001)
        self.assertEqual(total, 1)
        self.assertEqual(rows[0][0], 1001)
        self.assertEqual(rows[0][4], "Instagram фото")

    def test_user_search_accepts_numeric_id_and_username_prefix(self):
        self.assertEqual(database.find_admin_download_users("1002")[0][0], 1002)
        self.assertEqual(database.find_admin_download_users("@alice")[0][0], 1001)

    def test_journal_paginates_ten_records(self):
        for index in range(11):
            database.add_history(1001, f"https://instagram.com/p/{index}", "Instagram видео")
        first_page, total = database.get_admin_downloads_page(page=0, limit=10)
        second_page, _ = database.get_admin_downloads_page(page=1, limit=10)
        self.assertEqual((len(first_page), len(second_page), total), (10, 1, 11))


if __name__ == "__main__":
    unittest.main()
