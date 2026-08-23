import unittest

from downloaders.instagram import is_instagram_story_url, is_transient_instagram_error
from services import extract_service_link


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

    def test_transient_instagram_error_detection(self):
        self.assertTrue(is_transient_instagram_error(Exception("WinError 10060")))
        self.assertTrue(is_transient_instagram_error(Exception("connection reset")))
        self.assertFalse(is_transient_instagram_error(Exception("You need to log in")))


if __name__ == "__main__":
    unittest.main()
