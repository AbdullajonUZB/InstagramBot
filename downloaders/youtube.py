import asyncio
import logging
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
from utils.message_utils import get_message_target
from utils.download_limits import ensure_download_allowed
from utils.followup_media import remember_video_for_mp3

logger = logging.getLogger(__name__)
YOUTUBE_COOKIE_FILE = Path(__file__).resolve().parent.parent / "youtube_cookies.txt"
DENO_EXECUTABLE = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links" / "deno.exe"


def _youtube_runtime_options():
    options = {
        "extractor_args": {"youtube": {"player_client": ["default", "-android_sdkless"]}},
        "remote_components": ["ejs:github"],
    }
    if DENO_EXECUTABLE.exists():
        options["js_runtimes"] = {"deno": {"path": str(DENO_EXECUTABLE)}}
    return options


class YoutubeDownloader(BaseDownloader):
    def __init__(self, url: str, logger=None, temp_root=None):
        super().__init__(url=url, logger=logger, temp_root=temp_root)

    def _build_video_options(self):
        options = {
            "format": "best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "max_filesize": MAX_FILE_SIZE,
        }
        options.update(_youtube_runtime_options())
        if YOUTUBE_COOKIE_FILE.exists():
            options["cookiefile"] = str(YOUTUBE_COOKIE_FILE)
        return options

    def _build_audio_options(self):
        options = {
            "format": "bestaudio/best",
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

    async def _download_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = get_message_target(update)
        logger.info("[YouTube] 2/4 Downloading")

        try:
            filename = await asyncio.to_thread(
                self.download_media,
                "%(title)s.%(ext)s",
                self._build_video_options(),
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
            await send_video(update, str(file_path), t(update.effective_user.id, "youtube_video"))
        except (TimedOut, TelegramError) as error:
            logger.exception("[YouTube] Telegram send failed")
            await message.reply_text("⚠️ Не удалось отправить видео в Telegram. Попробуйте ещё раз.")
            return None
        except Exception as error:
            logger.exception("[YouTube] Telegram send failed")
            await message.reply_text("⚠️ Не удалось отправить видео в Telegram. Попробуйте ещё раз.")
            return None

        add_history(update.effective_user.id, self.url, "YouTube видео")
        increase_download_count(update.effective_user.id)
        logger.info("[YouTube] Successfully sent.")
        return True

    async def _download_audio(self, update: Update):
        message = get_message_target(update)
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
                await message.reply_audio(
                    audio=audio_file,
                    title=audio_file_path.stem,
                    performer="YouTube",
                    caption=t(update.effective_user.id, "youtube_audio"),
                    read_timeout=600,
                    write_timeout=600,
                    connect_timeout=60,
                    pool_timeout=60,
                )
        except (TimedOut, TelegramError) as error:
            logger.exception("[YouTube] Telegram send failed")
            await message.reply_text("⚠️ Не удалось отправить аудио в Telegram. Попробуйте ещё раз.")
            return None
        except Exception as error:
            logger.exception("[YouTube] Telegram send failed")
            await message.reply_text("⚠️ Не удалось отправить аудио в Telegram. Попробуйте ещё раз.")
            return None

        add_history(update.effective_user.id, self.url, "YouTube аудио")
        increase_download_count(update.effective_user.id)
        logger.info("[YouTube] Successfully sent.")
        return True

    async def download(self, update: Update, context: ContextTypes.DEFAULT_TYPE, choice: str = "video"):
        self.prepare_temp_dir()

        try:
            if not await ensure_download_allowed(update):
                return None

            logger.info("[YouTube] 1/4 Detecting URL")
            if choice == "audio":
                return await self._download_audio(update)
            return await self._download_video(update, context)
        finally:
            self.cleanup()


async def download_youtube(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    choice: str = "video",
):
    downloader = YoutubeDownloader(url=url, logger=logger)
    return await downloader.download(update, context, choice=choice)
