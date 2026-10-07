import unittest
from unittest.mock import AsyncMock, patch

from utils.bot_profile import (
    BOT_PROFILE_TEXT,
    BOT_SHORT_PROFILE_TEXT,
    configure_bot_profile,
    format_uptime,
)


class BotProfileTests(unittest.IsolatedAsyncioTestCase):
    async def test_profile_text_fits_telegram_limits(self):
        self.assertTrue(all(len(text) <= 512 for text in BOT_PROFILE_TEXT.values()))
        self.assertTrue(all(len(text) <= 120 for text in BOT_SHORT_PROFILE_TEXT.values()))

    async def test_profile_description_is_updated_for_fallback_and_languages(self):
        bot = type("BotStub", (), {
            "set_my_description": AsyncMock(return_value=True),
            "set_my_short_description": AsyncMock(return_value=True),
        })()

        await configure_bot_profile(bot)

        self.assertEqual(bot.set_my_description.await_count, 4)
        self.assertEqual(bot.set_my_short_description.await_count, 4)

    async def test_profile_api_failure_does_not_break_startup(self):
        bot = type("BotStub", (), {
            "set_my_description": AsyncMock(side_effect=RuntimeError("offline")),
            "set_my_short_description": AsyncMock(side_effect=RuntimeError("offline")),
        })()
        with patch("utils.bot_profile.logger.warning"):
            await configure_bot_profile(bot)
        self.assertEqual(bot.set_my_description.await_count, 4)

    def test_uptime_formatting(self):
        self.assertEqual(format_uptime(65), "1 мин.")
        self.assertEqual(format_uptime(3661), "1 ч. 1 мин.")
        self.assertEqual(format_uptime(90061), "1 дн. 1 ч. 1 мин.")


if __name__ == "__main__":
    unittest.main()
