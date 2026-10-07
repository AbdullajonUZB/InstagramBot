import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from utils.download_audit import _audit_text, audit_successful_download


class DownloadAuditTests(unittest.IsolatedAsyncioTestCase):
    def test_audit_text_includes_attribution_and_source(self):
        user = SimpleNamespace(
            username="sample_user",
            full_name="Sample User",
            first_name="Sample",
            id=12345,
        )

        text = _audit_text(user, "YouTube видео", "https://example.com/video")

        self.assertIn("@sample_user", text)
        self.assertIn("12345", text)
        self.assertIn("YouTube видео", text)
        self.assertIn("https://example.com/video", text)
        self.assertIn("Время (Ташкент)", text)

    async def test_successful_video_is_copied_with_activity_post(self):
        from utils import download_audit

        original_channel_id = download_audit.INLINE_CACHE_CHAT_ID
        download_audit.INLINE_CACHE_CHAT_ID = -100123
        try:
            bot = SimpleNamespace(
                send_message=AsyncMock(),
                send_video=AsyncMock(),
            )
            context = SimpleNamespace(bot=bot)
            user = SimpleNamespace(
                username="sample_user",
                full_name="Sample User",
                first_name="Sample",
                id=12345,
            )
            message = SimpleNamespace(video=SimpleNamespace(file_id="video-file-id"))

            await audit_successful_download(
                context,
                SimpleNamespace(effective_user=user),
                "https://example.com/video",
                "Facebook видео",
                message,
            )

            bot.send_message.assert_awaited_once()
            bot.send_video.assert_awaited_once_with(
                chat_id=-100123,
                video="video-file-id",
                supports_streaming=True,
                disable_notification=True,
            )
        finally:
            download_audit.INLINE_CACHE_CHAT_ID = original_channel_id


if __name__ == "__main__":
    unittest.main()
