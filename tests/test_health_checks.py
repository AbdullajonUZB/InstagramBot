import asyncio
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from handlers.health import health_report_text
from utils.health_checks import format_service_ping
from utils.uptime import format_uptime


class HealthCheckFormattingTests(unittest.TestCase):
    def test_connected_service_shows_latency(self):
        self.assertEqual(format_service_ping("YouTube", 42), "🟢 YouTube: 42 мс")

    def test_unavailable_service_is_marked(self):
        self.assertEqual(format_service_ping("Instagram", None), "🔴 Instagram: нет соединения")

    def test_uptime_formatting(self):
        self.assertEqual(format_uptime(65), "1 мин.")
        self.assertEqual(format_uptime(3661), "1 ч. 1 мин.")
        self.assertEqual(format_uptime(90061), "1 дн. 1 ч. 1 мин.")

    def test_health_report_includes_server_uptime_and_download_queue(self):
        async def scenario():
            application = SimpleNamespace(bot_data={
                "started_at": datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc),
                "started_monotonic": 1.0,
                "download_active": 2,
                "download_queue_waiting": {"a": {}, "b": {}},
            })
            with patch("handlers.health.get_admin_stats", return_value={"users": 1, "downloads_today": 2}), \
                 patch("handlers.health.collect_service_pings", return_value=[]), \
                 patch("handlers.health.time.monotonic", return_value=3661.0):
                return await health_report_text(application)

        text = asyncio.run(scenario())
        self.assertIn("Домашний сервер: запущен · работает 1 ч. 1 мин.", text)
        self.assertIn("выполняется 2 · в очереди 2", text)


if __name__ == "__main__":
    unittest.main()
