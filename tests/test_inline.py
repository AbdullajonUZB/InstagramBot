import unittest

from handlers.inline import INLINE_QUERY_MAX_LENGTH, build_inline_result
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


if __name__ == "__main__":
    unittest.main()
