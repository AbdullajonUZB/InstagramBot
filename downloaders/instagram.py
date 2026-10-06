import asyncio
import logging
import os
import re
import shutil
import subprocess
from urllib.parse import urlsplit
from pathlib import Path
from urllib.request import Request

from telegram import InputMediaPhoto, InputMediaVideo, Update
from telegram.ext import ContextTypes
from yt_dlp import YoutubeDL

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
from utils.media_cache import cache_message, make_cache_key

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


def is_instagram_story_profile_url(url: str) -> bool:
    return bool(re.search(r"/stories/(?!highlights/)[^/?#]+/?(?:\?[^#]*)?$", url, re.IGNORECASE))


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

    def _download_photo_post_fallback(self, ydl_options: dict) -> Path:
        """Fetch image entries directly and let yt-dlp download any video entries."""
        if self.temp_dir is None:
            raise RuntimeError("Instagram temporary directory was not initialized")

        options = {
            **ydl_options,
            "outtmpl": str(self.temp_dir / "instagram_%(id)s_%(playlist_index)s.%(ext)s"),
            "ignore_no_formats_error": True,
        }
        image_count = 0
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(self.url, download=False)
            if not info:
                raise RuntimeError("Instagram did not return post media metadata")

            entries = list(info.get("entries") or [info])
            video_entries = []
            photo_entries = []
            for entry in entries:
                if not entry:
                    continue
                formats = entry.get("formats") or []
                has_video = any(
                    media_format.get("vcodec") not in (None, "none")
                    for media_format in formats
                ) or entry.get("duration") is not None
                if has_video:
                    video_entries.append(entry)
                elif entry.get("thumbnails"):
                    photo_entries.append(entry)

            for index, entry in enumerate(photo_entries, start=1):
                thumbnails = [
                    thumb for thumb in entry.get("thumbnails", [])
                    if thumb.get("url")
                ]
                if not thumbnails:
                    continue
                image = max(
                    thumbnails,
                    key=lambda thumb: (thumb.get("width") or 0) * (thumb.get("height") or 0),
                )
                request = Request(
                    image["url"],
                    headers=entry.get("http_headers") or {
                        "Referer": "https://www.instagram.com/",
                    },
                )
                try:
                    with ydl.urlopen(request) as response:
                        content_type = response.headers.get("Content-Type", "").lower()
                        suffix = ".webp" if "image/webp" in content_type else ".jpg"
                        image_path = self.temp_dir / f"instagram_photo_{index:03d}{suffix}"
                        with image_path.open("wb") as image_file:
                            shutil.copyfileobj(response, image_file)
                    if image_path.stat().st_size:
                        image_count += 1
                except Exception as error:
                    self.logger.warning("Could not download Instagram photo %s: %s", index, error)

            if video_entries:
                video_playlist = {
                    **{key: value for key, value in info.items() if key != "entries"},
                    "_type": "playlist",
                    "entries": video_entries,
                }
                ydl.process_ie_result(video_playlist, download=True)

        files = self.get_downloaded_media_files()
        if not files:
            raise RuntimeError("Instagram post did not contain downloadable photos or videos")
        self.logger.info(
            "Instagram photo fallback completed: %s photos and %s media files",
            image_count,
            len(files),
        )
        return max(files, key=lambda path: path.stat().st_size)

    def _clear_partial_downloads(self):
        """Remove only this downloader's incomplete files before fallback extraction."""
        if self.temp_dir is None:
            return
        for path in self.temp_dir.iterdir():
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)

    async def _send_carousel(self, update: Update, files: list[Path], is_story: bool = False) -> bool:
        message = require_message_target(update)
        user = require_effective_user(update)
        media_items = []
        opened_files = []
        try:
            for file_path in files:
                if file_path.stat().st_size > MAX_FILE_SIZE:
                    await message.reply_text(t(user.id, "file_too_large"))
                    return False
                extension = file_path.suffix.lower()
                if extension in {".mp4", ".mov", ".mkv", ".webm"}:
                    file_path = await self._ensure_telegram_compatible_video(file_path)
                    if file_path.stat().st_size > MAX_FILE_SIZE:
                        await message.reply_text(t(user.id, "file_too_large"))
                        return False
                    handle = file_path.open("rb")
                    opened_files.append(handle)
                    media_items.append(InputMediaVideo(media=handle, supports_streaming=True))
                elif extension in {".jpg", ".jpeg", ".png", ".webp"}:
                    handle = file_path.open("rb")
                    opened_files.append(handle)
                    media_items.append(InputMediaPhoto(media=handle))

            if not media_items:
                return False
            media_items[0].caption = t(user.id, "instagram_stories" if is_story else "instagram_carousel")
            for start in range(0, len(media_items), 10):
                await message.reply_media_group(media=media_items[start:start + 10])
        finally:
            for handle in opened_files:
                handle.close()

        media_label = "Instagram Stories" if is_story else "Instagram карусель"
        add_history(user.id, self.url, f"{media_label} ({len(media_items)} медиа)")
        increase_download_count(user.id)
        return True

    async def download(self, update: Update, context: ContextTypes.DEFAULT_TYPE, story_mode: str = "one"):
        message = require_message_target(update)
        user = require_effective_user(update)
        is_story = is_instagram_story_url(self.url)

        if not await ensure_download_allowed(update):
            return None

        self.prepare_temp_dir()

        ydl_opts = {
            "cookiefile": "cookies.txt",
            "noplaylist": story_mode != "all",
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
                        "instagram_%(id)s_%(playlist_index)s.%(ext)s",
                        ydl_opts,
                    )
                    break
                except Exception as error:
                    last_download_error = error
                    if "no video formats found" in str(error).lower():
                        logger.info(
                            "Instagram post has photo entries without video streams; "
                            "retrying with photo-aware extraction"
                        )
                        self._clear_partial_downloads()
                        filename = await asyncio.to_thread(
                            self._download_photo_post_fallback,
                            ydl_opts,
                        )
                        break
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

            downloaded_media = self.get_downloaded_media_files()
            if story_mode == "video":
                downloaded_media = [
                    path for path in downloaded_media
                    if path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}
                ]
                if not downloaded_media:
                    await message.reply_text("⚠️ В этой Story нет видео.")
                    return False
            if len(downloaded_media) > 1:
                return await self._send_carousel(update, downloaded_media, is_story=is_story)

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
                    sent_message = await message.reply_photo(
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
                cache_message(make_cache_key(self.url, "instagram"), sent_message, "instagram_story_photo" if is_story else "instagram_photo")
                increase_download_count(user.id)
                return True

            if extension in video_formats:
                remember_video_for_mp3(context, file_path)
                file_path = await self._ensure_telegram_compatible_video(file_path)
                size = file_path.stat().st_size
                if size > MAX_FILE_SIZE:
                    await message.reply_text(t(user.id, "file_too_large"))
                    return False

                sent_message = await send_video(
                    update,
                    str(file_path),
                    t(
                        user.id,
                        "instagram_story_video" if is_story else "instagram_video",
                    ),
                )
                cache_message(make_cache_key(self.url, "instagram"), sent_message, "instagram_story_video" if is_story else "instagram_video")
                add_history(
                    user.id,
                    self.url,
                    "Instagram Story видео" if is_story else "Видео",
                )
                increase_download_count(user.id)
                return True

            with open(file_path, "rb") as document:
                sent_message = await message.reply_document(
                    document=document,
                    caption=t(user.id, "instagram_document"),
                )
            cache_message(make_cache_key(self.url, "instagram"), sent_message, "instagram_document")
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
    story_mode: str = "one",
):
    downloader = InstagramDownloader(url=normalize_instagram_reel_url(url), logger=logger)
    return await downloader.download(update, context, story_mode=story_mode)
