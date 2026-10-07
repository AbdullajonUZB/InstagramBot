import asyncio
import unittest
from types import SimpleNamespace

from utils.download_queue import run_queued_download


class DownloadQueueHealthTests(unittest.TestCase):
    def test_active_download_counter_is_cleared_after_success_or_error(self):
        async def scenario(raise_error=False):
            data = {}
            context = SimpleNamespace(
                application=SimpleNamespace(bot_data=data),
                user_data={},
            )

            class Message:
                async def edit_text(self, *_args, **_kwargs):
                    pass

            async def download():
                self.assertEqual(data["download_active"], 1)
                if raise_error:
                    raise RuntimeError("download failed")
                return True

            try:
                result = await run_queued_download(context, Message(), download())
            except RuntimeError:
                return None, data
            return result, data

        result, data = asyncio.run(scenario())
        self.assertTrue(result)
        self.assertEqual(data["download_active"], 0)

        result, data = asyncio.run(scenario(raise_error=True))
        self.assertIsNone(result)
        self.assertEqual(data["download_active"], 0)


if __name__ == "__main__":
    unittest.main()
