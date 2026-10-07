import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from handlers.inline import (
    INLINE_QUERY_MAX_LENGTH,
    INLINE_TRIAL_LIMIT,
    build_inline_result,
    build_cached_video_result,
    build_video_result,
    extract_direct_video,
    _find_direct_video,
    _cache_download_options,
)
from services import extract_service_link


class InlineModeTests(unittest.TestCase):
    def test_supported_link_builds_shareable_result_and_bot_button(self):
        service, url = extract_service_link("https://youtu.be/abc123")
        result = build_inline_result(service, url, "example_bot")

        self.assertEqual(result.title, "📥 Ссылка из YouTube")
        self.assertIn(url, result.input_message_content.message_text)
        self.assertEqual(
            result.reply_markup.inline_keyboard[0][0].url,
            "https://t.me/example_bot",
        )

    def test_untrusted_service_link_is_not_detected(self):
        self.assertEqual(
            extract_service_link("https://example.com/watch?v=abc123"),
            (None, None),
        )

    def test_inline_query_length_is_bounded(self):
        self.assertEqual(INLINE_QUERY_MAX_LENGTH, 2000)

    def test_direct_mp4_metadata_becomes_inline_video(self):
        metadata = {
            "title": "Demo video",
            "thumbnail": "https://cdn.example/thumb.jpg",
            "formats": [
                {
                    "url": "https://cdn.example/video.mp4",
                    "ext": "mp4",
                    "vcodec": "avc1",
                    "acodec": "mp4a",
                    "height": 720,
                    "filesize": 1_000_000,
                }
            ],
        }
        with patch("handlers.inline.YoutubeDL") as ydl:
            ydl.return_value.__enter__.return_value.extract_info.return_value = metadata
            video = extract_direct_video("youtube", "https://youtu.be/abc123")

        self.assertEqual(video["url"], "https://cdn.example/video.mp4")
        result = build_video_result("youtube", "https://youtu.be/abc123", video, 1, "example_bot")
        self.assertEqual(result.video_url, "https://cdn.example/video.mp4")
        self.assertEqual(result.reply_markup.inline_keyboard[0][0].url, "https://t.me/example_bot")

    def test_direct_video_rejects_audio_only_and_oversized_formats(self):
        metadata = {
            "title": "Demo video",
            "thumbnail": "https://cdn.example/thumb.jpg",
            "formats": [
                {
                    "url": "https://cdn.example/audio.mp4",
                    "ext": "mp4",
                    "vcodec": "none",
                    "acodec": "mp4a",
                },
                {
                    "url": "https://cdn.example/large.mp4",
                    "ext": "mp4",
                    "vcodec": "avc1",
                    "acodec": "mp4a",
                    "filesize": 100_000_000,
                },
            ],
        }
        with patch("handlers.inline.YoutubeDL") as ydl:
            ydl.return_value.__enter__.return_value.extract_info.return_value = metadata
            video = extract_direct_video("youtube", "https://youtu.be/abc123")
        self.assertIsNone(video)

    def test_direct_video_with_referer_requirement_uses_cache_fallback(self):
        metadata = {
            "title": "Restricted video",
            "thumbnail": "https://cdn.example/thumb.jpg",
            "formats": [
                {
                    "url": "https://cdn.example/restricted.mp4",
                    "ext": "mp4",
                    "vcodec": "avc1",
                    "acodec": "mp4a",
                    "protocol": "https",
                    "http_headers": {"Referer": "https://www.instagram.com/"},
                }
            ],
        }
        self.assertIsNone(_find_direct_video(metadata))

    def test_cached_video_result_uses_telegram_file_id(self):
        result = build_cached_video_result(
            "facebook",
            "https://facebook.com/reel/123",
            "telegram-file-id",
            2,
            "example_bot",
        )
        self.assertEqual(result.video_file_id, "telegram-file-id")
        self.assertEqual(result.description, "Пробный результат 2/3")

    def test_cache_download_options_enable_download(self):
        class DownloaderStub:
            def _build_video_options(self, quality):
                return {"format": "18", "skip_download": True}

        options = _cache_download_options("youtube", DownloaderStub())
        self.assertNotIn("skip_download", options)
        self.assertTrue(options["noplaylist"])

    def test_inline_trial_quota_is_persistent_and_limited(self):
        from database import database

        with tempfile.TemporaryDirectory() as directory:
            test_db = Path(directory) / "inline.db"
            with patch.object(database, "DB_NAME", str(test_db)):
                database.create_database()
                for index in range(INLINE_TRIAL_LIMIT):
                    allowed, used = database.consume_inline_trial(123, f"query-{index}", INLINE_TRIAL_LIMIT)
                    self.assertTrue(allowed)
                    self.assertEqual(used, index + 1)
                allowed, used = database.consume_inline_trial(123, "query-0", INLINE_TRIAL_LIMIT)
                self.assertTrue(allowed)
                self.assertEqual(used, INLINE_TRIAL_LIMIT)
                allowed, used = database.consume_inline_trial(123, "query-over-limit", INLINE_TRIAL_LIMIT)
                self.assertFalse(allowed)
                self.assertEqual(used, INLINE_TRIAL_LIMIT)
                allowed, used = database.consume_inline_trial(456, "query-other-user", INLINE_TRIAL_LIMIT)
                self.assertTrue(allowed)
                self.assertEqual(used, 1)


if __name__ == "__main__":
    unittest.main()
