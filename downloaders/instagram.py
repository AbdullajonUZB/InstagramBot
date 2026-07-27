import asyncio
import logging
import os
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from config import MAX_FILE_SIZE
from database.database import (
    add_history,
    can_download,
    increase_download_count,
    register_user,
)
from downloaders.base import BaseDownloader
from utils.i18n import t
from utils.media_sender import send_video

logger = logging.getLogger(__name__)


class InstagramDownloader(BaseDownloader):
    def __init__(self, url: str, logger=None, temp_root=None):
        super().__init__(url=url, logger=logger, temp_root=temp_root)

    async def download(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user

        register_user(
            user.id,
            user.username,
            user.first_name,
        )

        if not can_download(user.id):
            await update.message.reply_text(
                "🚫 Вы использовали все 10 бесплатных скачиваний на сегодня.\n\n"
                "Попробуйте снова завтра или оформите Premium ⭐"
            )
            return

        self.prepare_temp_dir()

        ydl_opts = {
            "cookiefile": "cookies.txt",
            "noplaylist": True,
            "merge_output_format": "mp4",
            "retries": 10,
            "fragment_retries": 10,
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
            filename = await asyncio.to_thread(
                self.download_media,
                "%(title)s.%(ext)s",
                ydl_opts,
            )

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
                    await update.message.reply_photo(
                        photo=photo,
                        caption=t(update.effective_user.id, "instagram_photo"),
                    )
                add_history(update.effective_user.id, self.url, "Фото")
                increase_download_count(update.effective_user.id)
                return True

            if extension in video_formats:
                size = file_path.stat().st_size
                if size > MAX_FILE_SIZE:
                    await update.message.reply_text(t(update.effective_user.id, "file_too_large"))
                    return False

                await send_video(
                    update,
                    str(file_path),
                    t(update.effective_user.id, "instagram_video"),
                )
                add_history(update.effective_user.id, self.url, "Видео")
                increase_download_count(update.effective_user.id)
                return True

            with open(file_path, "rb") as document:
                await update.message.reply_document(
                    document=document,
                    caption=t(update.effective_user.id, "instagram_document"),
                )
            add_history(update.effective_user.id, self.url, "Документ")
            increase_download_count(update.effective_user.id)
            return True

        except Exception as error:
            await self.handle_error(update, error, "instagram_error", "Instagram ERROR")
            return False

        finally:
            self.cleanup()


async def download_instagram(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
):
    downloader = InstagramDownloader(url=url, logger=logger)
    return await downloader.download(update, context)
