import unittest

from downloaders.instagram import is_instagram_story_profile_url, is_instagram_story_url, is_transient_instagram_error
from services import extract_service_link
from downloaders.facebook import FACEBOOK_FORMAT
from downloaders.youtube import _youtube_runtime_options
from downloaders.youtube import YoutubeDownloader
from handlers.history import history_keyboard
from downloaders.base import MEDIA_EXTENSIONS
from handlers.admin import admin_panel_keyboard


class RoutingTests(unittest.TestCase):
    def test_supported_services_are_detected(self):
        cases = {
            "instagram": "https://www.instagram.com/reel/abc123/",
            "youtube": "https://youtu.be/abc123",
            "tiktok": "https://www.tiktok.com/@user/video/123",
            "pinterest": "https://pin.it/abc123",
            "facebook": "https://www.facebook.com/watch/?v=123",
        }
        for expected_service, url in cases.items():
            with self.subTest(expected_service=expected_service):
                service, detected_url = extract_service_link(f"Ссылка: {url}.")
                self.assertEqual(service, expected_service)
                self.assertEqual(detected_url, url)

    def test_instagram_story_urls(self):
        self.assertTrue(is_instagram_story_url("https://www.instagram.com/stories/user/123/"))
        self.assertTrue(is_instagram_story_url("https://www.instagram.com/stories/highlights/123/"))
        self.assertFalse(is_instagram_story_url("https://www.instagram.com/p/abc123/"))
        self.assertTrue(is_instagram_story_profile_url("https://www.instagram.com/stories/user/"))
        self.assertFalse(is_instagram_story_profile_url("https://www.instagram.com/stories/user/123/"))

    def test_transient_instagram_error_detection(self):
        self.assertTrue(is_transient_instagram_error(Exception("WinError 10060")))
        self.assertTrue(is_transient_instagram_error(Exception("connection reset")))
        self.assertFalse(is_transient_instagram_error(Exception("You need to log in")))

    def test_facebook_format_prioritizes_telegram_compatible_streams(self):
        self.assertIn("format_id=sd", FACEBOOK_FORMAT)
        self.assertIn("height<=1280", FACEBOOK_FORMAT)
        self.assertIn("vcodec^=avc", FACEBOOK_FORMAT)

    def test_youtube_runtime_options_have_a_safe_fallback(self):
        options = _youtube_runtime_options()
        self.assertIn("js_runtimes", options)
        self.assertIn("deno", options["js_runtimes"])
        self.assertNotIn("remote_components", options)
        self.assertIn("youtubepot-bgutilscript", options["extractor_args"])

    def test_youtube_quality_selectors_are_supported(self):
        downloader = YoutubeDownloader("https://youtu.be/test")
        self.assertIn("height<=720", downloader._build_video_options("720")["format"])
        self.assertIn("height<=480", downloader._build_video_options("480")["format"])
        self.assertEqual(downloader._build_video_options("auto")["format"], "18/best[ext=mp4]/best")

    def test_history_keyboard_contains_download_buttons(self):
        keyboard = history_keyboard([
            ("Instagram видео", "https://www.instagram.com/reel/test/", "today"),
            ("YouTube аудио", "https://youtu.be/test", "today"),
        ])
        callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
        self.assertEqual(callbacks, ["history:download:1", "history:download:2"])

    def test_carousel_media_extensions_include_photos_and_videos(self):
        self.assertIn(".mp4", MEDIA_EXTENSIONS)
        self.assertIn(".jpg", MEDIA_EXTENSIONS)

    def test_admin_panel_has_dashboard_controls(self):
        callbacks = [
            button.callback_data
            for row in admin_panel_keyboard().inline_keyboard
            for button in row
        ]
        self.assertIn("admin_panel:status", callbacks)
        self.assertIn("admin_panel:users", callbacks)
        self.assertIn("admin_panel:security", callbacks)


if __name__ == "__main__":
    unittest.main()
