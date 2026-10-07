import unittest

from utils.health_checks import format_service_ping


class HealthCheckFormattingTests(unittest.TestCase):
    def test_connected_service_shows_latency(self):
        self.assertEqual(format_service_ping("YouTube", 42), "🟢 YouTube: 42 мс")

    def test_unavailable_service_is_marked(self):
        self.assertEqual(format_service_ping("Instagram", None), "🔴 Instagram: нет соединения")


if __name__ == "__main__":
    unittest.main()
