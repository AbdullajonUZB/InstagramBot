import asyncio
import logging
import os
import re
import shutil
import subprocess
from urllib.parse import urlsplit
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from config import MAX_FILE_SIZE
from database.database import (
    add_history,
    increase_download_count,
)
from downloaders.base import BaseDownloader
from utils.i18n import t
from utils.media_sender import send_video
from utils.message_utils import require_effective_user, require_message_target
from utils.download_limits import ensure_download_allowed
from utils.followup_media import remember_video_for_mp3

logger = logging.getLogger(__name__)


def is_transient_instagram_error(error: Exception) -> bool:
    error_text = str(error).lower()
    return any(
        marker in error_text
        for marker in (
            "winerror 10060",
            "timed out",
            "timeout",
            "transporterror",
            "connection reset",
            "connection refused",
            "temporary failure",
        )
    )


def is_instagram_story_url(url: str) -> bool:
    return bool(re.search(r"/stories/(?:highlights/)?[^/?#]+", url, re.IGNORECASE))


def normalize_instagram_reel_url(url: str) -> str:
    """Canonicalize Reel links and discard Instagram query parameters."""
    parsed = urlsplit(url.strip())
    match = re.search(r"/(?:reel|reels)/([^/?#]+)/?", parsed.path, re.IGNORECASE)
    if not match:
        return url
    return f"https://www.instagram.com/reels/{match.group(1)}/"


class InstagramDownloader(BaseDownloader):
    def __init__(self, url: str, logger=None, temp_root=None):
        super().__init__(url=url, logger=logger, temp_root=temp_root)

    async def _ensure_telegram_compatible_video(self, file_path: Path) -> Path:
        """Transcode only non-H.264 video streams to Telegram-safe MP4."""
        ffprobe = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
        ffmpeg = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
        if not ffprobe or not ffmpeg:
            logger.warning("ffprobe/ffmpeg not available; keeping downloaded video")
            return file_path

        probe = await asyncio.to_thread(
            subprocess.run,
            [ffprobe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1",
             str(file_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        codec = probe.stdout.strip().lower()
        if codec in {"h264", "avc1"}:
            logger.info("Instagram video codec is already H.264; skipping transcode")
            return file_path

        output_path = file_path.with_name(f"{file_path.stem}_telegram.mp4")
        logger.info("Transcoding Instagram video from %s to H.264/AAC", codec or "unknown")
        result = await asyncio.to_thread(
            subprocess.run,
            [ffmpeg, "-y", "-i", str(file_path), "-c:v", "libx264",
             "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac",
             "-movflags", "+faststart", str(output_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not output_path.exists():
            raise RuntimeError("Instagram video transcoding failed")
        file_path.unlink(missing_ok=True)
        return output_path

    async def download(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = require_message_target(update)
        user = require_effective_user(update)
        is_story = is_instagram_story_url(self.url)

        if not await ensure_download_allowed(update):
            return None

        self.prepare_temp_dir()

        ydl_opts = {
            "cookiefile": "cookies.txt",
            "noplaylist": True,
            # Prefer Telegram-compatible H.264/MP4 + AAC/M4A. The fallbacks
            # still require a video-capable format and never request audio-only.
            "format": "bv*[ext=mp4][vcodec^=avc]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
            "merge_output_format": "mp4",
            "retries": 10,
            "fragment_retries": 10,
            "extractor_retries": 5,
            "socket_timeout": 60,
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/138.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
        }

        try:
            filename = None
            last_download_error = None
            for attempt in range(3):
                try:
                    filename = await asyncio.to_thread(
                        self.download_media,
                        "%(title)s.%(ext)s",
                        ydl_opts,
                    )
                    break
                except Exception as error:
                    last_download_error = error
                    if not is_transient_instagram_error(error) or attempt == 2:
                        raise
                    delay = 2 ** attempt
                    logger.warning(
                        "Instagram request failed (attempt %s/3); retrying in %s seconds",
                        attempt + 1,
                        delay,
                    )
                    await asyncio.sleep(delay)

            if filename is None:
                raise last_download_error or RuntimeError("Instagram download failed")

            file_path, validation_result = await self.resolve_validated_file(
                update,
                filename,
                max_size=MAX_FILE_SIZE,
                missing_return=True,
                too_large_return=False,
            )
            if validation_result is not None:
                return validation_result
            if file_path is None:
                return True

            extension = os.path.splitext(str(file_path))[1].lower()

            image_formats = [".jpg", ".jpeg", ".png", ".webp"]
            video_formats = [".mp4", ".mov", ".mkv", ".webm"]

            if extension in image_formats:
                with open(file_path, "rb") as photo:
                    await message.reply_photo(
                        photo=photo,
                        caption=t(
                            user.id,
                            "instagram_story_photo" if is_story else "instagram_photo",
                        ),
                    )
                add_history(
                    user.id,
                    self.url,
                    "Instagram Story фото" if is_story else "Фото",
                )
                increase_download_count(user.id)
                return True

            if extension in video_formats:
                remember_video_for_mp3(context, file_path)
                file_path = await self._ensure_telegram_compatible_video(file_path)
                size = file_path.stat().st_size
                if size > MAX_FILE_SIZE:
                    await message.reply_text(t(user.id, "file_too_large"))
                    return False

                await send_video(
                    update,
                    str(file_path),
                    t(
                        user.id,
                        "instagram_story_video" if is_story else "instagram_video",
                    ),
                )
                add_history(
                    user.id,
                    self.url,
                    "Instagram Story видео" if is_story else "Видео",
                )
                increase_download_count(user.id)
                return True

            with open(file_path, "rb") as document:
                await message.reply_document(
                    document=document,
                    caption=t(user.id, "instagram_document"),
                )
            add_history(user.id, self.url, "Документ")
            increase_download_count(user.id)
            return True

        except Exception as error:
            error_text = str(error).lower()
            if is_story and ("login" in error_text or "cookies" in error_text):
                logger.warning("Instagram Story requires an authenticated session: %s", error)
                await message.reply_text(
                    t(user.id, "instagram_story_login_required")
                )
                return False
            if is_transient_instagram_error(error):
                logger.warning("Instagram is temporarily unavailable: %s", error)
                try:
                    await message.reply_text(
                        t(user.id, "instagram_unavailable")
                    )
                except Exception:
                    pass
                return None
            await self.handle_error(update, error, "instagram_error", "Instagram ERROR")
            return False

        finally:
            self.cleanup()


async def download_instagram(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
):
    downloader = InstagramDownloader(url=normalize_instagram_reel_url(url), logger=logger)
    return await downloader.download(update, context)
