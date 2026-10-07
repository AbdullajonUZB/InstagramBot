import asyncio
import functools
import logging
import os
import shutil
import subprocess
from pathlib import Path

from telegram import Update
from telegram.error import TelegramError, TimedOut
from telegram.ext import ContextTypes

from config import MAX_FILE_SIZE
from database.database import add_history, increase_download_count
from downloaders.base import BaseDownloader
from keyboards.navigation import back_to_main_menu_keyboard
from utils.i18n import t
from utils.media_sender import send_video
from utils.message_utils import require_effective_user, require_message_target
from utils.download_limits import ensure_download_allowed
from utils.followup_media import remember_video_for_mp3
from utils.media_cache import cache_message, make_cache_key

logger = logging.getLogger(__name__)
YOUTUBE_COOKIE_FILE = Path(__file__).resolve().parent.parent / "youtube_cookies.txt"
DENO_EXECUTABLE = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links" / "deno.exe"


@functools.lru_cache(maxsize=1)
def _deno_is_fast_enough() -> bool:
    """Avoid enabling bgutil when Deno hangs during its startup check."""
    executable = str(DENO_EXECUTABLE) if DENO_EXECUTABLE.exists() else shutil.which("deno")
    if not executable:
        return False
    try:
        completed = subprocess.run(
            [executable, "--version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.warning("Deno отвечает слишком долго; bgutil POT-провайдер отключён")
        return False
    return completed.returncode == 0


def _youtube_runtime_options():
    options = {
        "extractor_args": {
            "youtube": {"player_client": ["mweb"]},
            # Внешний bgutil-провайдер иногда зависает на проверке Deno
            # и блокирует получение форматов на 15 секунд.
            "youtubepot-bgutilscript": {"server_home": os.devnull},
        },
    }
    if _deno_is_fast_enough():
        options["js_runtimes"] = {"deno": {"path": str(DENO_EXECUTABLE)}}
    else:
        # Не даём установленному, но зависающему Deno автоматически
        # подхватиться плагину bgutil-ytdlp-pot-provider.
        options["js_runtimes"] = {"deno": {"path": os.devnull}}
    return options


class YoutubeDownloader(BaseDownloader):
    def __init__(self, url: str, logger=None, temp_root=None):
        super().__init__(url=url, logger=logger, temp_root=temp_root)

    def _build_video_options(self, quality: str = "auto"):
        formats = {
            "auto": "18/best[ext=mp4]/best",
            "720": "best[height<=720][ext=mp4]/best[height<=720]/18/best[ext=mp4]/best",
            "480": "best[height<=480][ext=mp4]/best[height<=480]/18/best[ext=mp4]/best",
            "original": "bestvideo+bestaudio/best",
        }
        options = {
            "format": formats.get(quality, formats["auto"]),
            "merge_output_format": "mp4",
            "max_filesize": MAX_FILE_SIZE,
        }
        options.update(_youtube_runtime_options())
        if YOUTUBE_COOKIE_FILE.exists():
            options["cookiefile"] = str(YOUTUBE_COOKIE_FILE)
        return options

    def _build_audio_options(self):
        options = {
            "format": "18/bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "0",
                }
            ],
            "quiet": True,
            "no_warnings": True,
        }
        options.update(_youtube_runtime_options())
        if YOUTUBE_COOKIE_FILE.exists():
            options["cookiefile"] = str(YOUTUBE_COOKIE_FILE)
        return options

    async def _download_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE, quality: str = "auto"):
        message = require_message_target(update)
        user = require_effective_user(update)
        logger.info("[YouTube] 2/4 Downloading")

        try:
            filename = await asyncio.to_thread(
                self.download_media,
                "%(title)s.%(ext)s",
                self._build_video_options(quality),
            )
        except Exception as error:
            logger.exception("[YouTube] Download stage failed")
            await message.reply_text("❌ Не удалось скачать видео.", reply_markup=back_to_main_menu_keyboard())
            return False

        try:
            file_path, validation_result = await self.resolve_validated_file(
                update,
                filename,
                max_size=MAX_FILE_SIZE,
                missing_return=False,
                too_large_return=False,
            )
        except Exception as error:
            logger.exception("[YouTube] Validation stage failed")
            await message.reply_text("❌ Не удалось скачать видео.", reply_markup=back_to_main_menu_keyboard())
            return False

        if validation_result is not None:
            return validation_result
        if file_path is None:
            return False

        logger.info("[YouTube] 4/4 Uploading to Telegram")
        try:
            remember_video_for_mp3(context, file_path)
            sent_message = await send_video(update, str(file_path), t(user.id, "youtube_video"))
            cache_message(make_cache_key(self.url, f"youtube:video:{quality}"), sent_message, "youtube_video")
        except (TimedOut, TelegramError) as error:
            logger.exception("[YouTube] Telegram send failed")
            await message.reply_text("⚠️ Не удалось отправить видео в Telegram. Попробуйте ещё раз.")
            return None
        except Exception as error:
            logger.exception("[YouTube] Telegram send failed")
            await message.reply_text("⚠️ Не удалось отправить видео в Telegram. Попробуйте ещё раз.")
            return None

        add_history(user.id, self.url, "YouTube видео")
        increase_download_count(user.id)
        logger.info("[YouTube] Successfully sent.")
        return True

    async def _download_audio(self, update: Update):
        message = require_message_target(update)
        user = require_effective_user(update)
        logger.info("[YouTube] 2/4 Downloading")

        try:
            filename = await asyncio.to_thread(
                self.download_media,
                "%(title)s.%(ext)s",
                self._build_audio_options(),
            )
        except Exception as error:
            logger.exception("[YouTube] Download stage failed")
            await message.reply_text("❌ Не удалось скачать аудио.", reply_markup=back_to_main_menu_keyboard())
            return False

        logger.info("[YouTube] 3/4 Converting to MP3")
        try:
            audio_file_path = self.resolve_downloaded_file(filename)
            if audio_file_path is None or not audio_file_path.exists():
                raise RuntimeError("download_failed")

            if audio_file_path.suffix.lower() != ".mp3":
                mp3_path = audio_file_path.with_suffix(".mp3")
                completed = await asyncio.to_thread(
                    subprocess.run,
                    ["ffmpeg", "-y", "-i", str(audio_file_path), str(mp3_path)],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if completed.returncode != 0:
                    raise RuntimeError("conversion_failed")
                audio_file_path = mp3_path

            if not audio_file_path.exists():
                raise RuntimeError("conversion_failed")
        except RuntimeError as error:
            logger.exception("[YouTube] Conversion stage failed")
            await message.reply_text("❌ Не удалось обработать аудио в MP3.", reply_markup=back_to_main_menu_keyboard())
            return False
        except Exception as error:
            logger.exception("[YouTube] Conversion stage failed")
            await message.reply_text("❌ Не удалось обработать аудио в MP3.", reply_markup=back_to_main_menu_keyboard())
            return False

        logger.info("[YouTube] 4/4 Uploading to Telegram")
        try:
            with audio_file_path.open("rb") as audio_file:
                sent_message = await message.reply_audio(
                    audio=audio_file,
                    title=audio_file_path.stem,
                    performer="YouTube",
                    caption=t(user.id, "youtube_audio"),
                    read_timeout=600,
                    write_timeout=600,
                    connect_timeout=60,
                    pool_timeout=60,
                )
            cache_message(make_cache_key(self.url, "youtube:audio"), sent_message, "youtube_audio")
        except (TimedOut, TelegramError) as error:
            logger.exception("[YouTube] Telegram send failed")
            await message.reply_text("⚠️ Не удалось отправить аудио в Telegram. Попробуйте ещё раз.")
            return None
        except Exception as error:
            logger.exception("[YouTube] Telegram send failed")
            await message.reply_text("⚠️ Не удалось отправить аудио в Telegram. Попробуйте ещё раз.")
            return None

        add_history(user.id, self.url, "YouTube аудио")
        increase_download_count(user.id)
        logger.info("[YouTube] Successfully sent.")
        return True

    async def download(self, update: Update, context: ContextTypes.DEFAULT_TYPE, choice: str = "video", quality: str = "auto"):
        self.prepare_temp_dir()

        try:
            if not await ensure_download_allowed(update):
                return None

            logger.info("[YouTube] 1/4 Detecting URL")
            if choice == "audio":
                return await self._download_audio(update)
            return await self._download_video(update, context, quality=quality)
        finally:
            self.cleanup()


async def download_youtube(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    choice: str = "video",
    quality: str = "auto",
):
    downloader = YoutubeDownloader(url=url, logger=logger)
    downloader.progress_callback = context.user_data.get("download_progress_callback")
    return await downloader.download(update, context, choice=choice, quality=quality)
