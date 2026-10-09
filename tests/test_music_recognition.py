import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from database import database
from utils import music_recognition


class MusicRecognitionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(
            database, "DB_NAME", str(Path(self.temp_dir.name) / "test.db")
        )
        self.db_patch.start()
        database.create_database()

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_request_budget_is_persistent_and_hard_capped(self):
        self.assertTrue(database.reserve_audd_recognition_request(2))
        self.assertTrue(database.reserve_audd_recognition_request(2))
        self.assertFalse(database.reserve_audd_recognition_request(2))
        self.assertFalse(database.reserve_audd_recognition_request(0))

    async def test_recognition_sends_short_sample_and_returns_track_metadata(self):
        source_path = Path(self.temp_dir.name) / "video.mp4"
        source_path.write_bytes(b"video")
        response = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "status": "success",
                "result": {"title": "Song", "artist": "Artist"},
            },
        )
        client = AsyncMock()
        client.post.return_value = response
        async_context = AsyncMock()
        async_context.__aenter__.return_value = client

        def create_sample(_source, sample_path):
            Path(sample_path).write_bytes(b"short audio")

        with (
            patch.object(music_recognition, "AUDD_API_TOKEN", "test-token"),
            patch.object(music_recognition.httpx, "AsyncClient", return_value=async_context),
            patch.object(music_recognition, "_extract_sample", side_effect=create_sample),
        ):
            result = await music_recognition.recognize_track(source_path, 1)

        self.assertEqual(result["title"], "Song")
        self.assertEqual(result["artist"], "Artist")
        client.post.assert_awaited_once()
        self.assertEqual(client.post.await_args.kwargs["data"]["api_token"], "test-token")
        self.assertFalse(database.reserve_audd_recognition_request(1))


if __name__ == "__main__":
    unittest.main()
