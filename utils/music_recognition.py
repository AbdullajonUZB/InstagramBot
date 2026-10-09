"""Small audio fingerprint lookup through the official AudD API."""

import asyncio
import subprocess
import tempfile
from pathlib import Path

import httpx

from config import AUDD_API_TOKEN
from database.database import reserve_audd_recognition_request
from utils.media_converter import get_ffmpeg_path


AUDD_ENDPOINT = "https://api.audd.io/"
SAMPLE_SECONDS = 12
MAX_SAMPLE_BYTES = 5 * 1024 * 1024


class MusicRecognitionError(RuntimeError):
    pass


class MusicRecognitionLimitReached(MusicRecognitionError):
    pass


def _extract_sample(video_path: Path, sample_path: Path):
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        raise MusicRecognitionError("FFmpeg не найден на компьютере бота.")
    result = subprocess.run(
        [
            ffmpeg, "-y", "-ss", "0", "-i", str(video_path), "-t",
            str(SAMPLE_SECONDS), "-vn", "-ac", "1", "-ar", "44100",
            "-b:a", "96k", str(sample_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0 or not sample_path.exists():
        raise MusicRecognitionError("В видео не удалось извлечь аудиофрагмент.")
    if sample_path.stat().st_size > MAX_SAMPLE_BYTES:
        raise MusicRecognitionError("Аудиофрагмент слишком большой для распознавания.")


async def recognize_track(video_path: str | Path, max_requests: int) -> dict | None:
    """Extract one short sample and return AudD metadata, or None if unmatched."""
    if not AUDD_API_TOKEN:
        raise MusicRecognitionError("Распознавание пока не настроено: отсутствует API-токен.")

    source = Path(video_path)
    if not source.is_file():
        raise MusicRecognitionError("Исходный видеофайл больше недоступен.")

    try:
        with tempfile.TemporaryDirectory(prefix="music_recognition_") as temp_dir:
            sample_path = Path(temp_dir) / "sample.mp3"
            await asyncio.to_thread(_extract_sample, source, sample_path)
            if not reserve_audd_recognition_request(max_requests):
                raise MusicRecognitionLimitReached("Recognition request cap reached.")
            with sample_path.open("rb") as sample:
                async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
                    response = await client.post(
                        AUDD_ENDPOINT,
                        data={"api_token": AUDD_API_TOKEN},
                        files={"file": ("sample.mp3", sample, "audio/mpeg")},
                    )
            response.raise_for_status()
            payload = response.json()
    except MusicRecognitionError:
        raise
    except (httpx.HTTPError, ValueError, OSError, subprocess.TimeoutExpired) as error:
        raise MusicRecognitionError("Сервис распознавания временно недоступен.") from error

    if payload.get("status") != "success":
        raise MusicRecognitionError("Сервис распознавания не смог обработать аудио.")
    result = payload.get("result")
    if not isinstance(result, dict) or not result.get("title"):
        return None
    return result
