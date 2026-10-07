import unittest
from pathlib import Path

from utils.i18n import TRANSLATIONS


class WelcomeInformationTests(unittest.TestCase):
    def test_welcome_explains_hours_home_hosting_and_limits_in_all_languages(self):
        for language in ("ru", "uz", "en"):
            with self.subTest(language=language):
                text = TRANSLATIONS[language]["welcome"]
                self.assertIn("08:00–00:00", text)
                self.assertIn("16", text)
                self.assertNotIn("TikTok", text)

    def test_start_banner_asset_is_present_and_reasonably_sized(self):
        banner = Path(__file__).resolve().parents[1] / "assets" / "welcome_banner.png"
        self.assertTrue(banner.is_file())
        self.assertLess(banner.stat().st_size, 10 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
