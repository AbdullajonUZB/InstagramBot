import asyncio
import logging
import os
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from config import MAX_FILE_SIZE
from database.database import add_history
from downloaders.base import BaseDownloader
from utils.i18n import t
from utils.media_sender import send_video

logger = logging.getLogger(__name__)


class PinterestDownloader(BaseDownloader):
    def __init__(self, url: str, logger=None, temp_root=None):
        super().__init__(url=url, logger=logger, temp_root=temp_root)

    async def download(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.prepare_temp_dir()

        try:
            filename = await asyncio.to_thread(
                self.download_media,
                "%(title)s.%(ext)s",
                {
                    "max_filesize": MAX_FILE_SIZE,
                },
            )

            file_path, validation_result = await self.resolve_validated_file(
                update,
                filename,
                max_size=MAX_FILE_SIZE,
                missing_return=False,
                too_large_return=False,
            )
            if validation_result is not None:
                return validation_result
            if file_path is None:
                return False

            extension = os.path.splitext(str(file_path))[1].lower()

            if extension in {".jpg", ".jpeg", ".png", ".webp"}:
                with open(file_path, "rb") as photo:
                    await update.message.reply_photo(
                        photo=photo,
                        caption=t(update.effective_user.id, "pinterest_photo"),
                    )
                media_type = "Pinterest фото"
            else:
                await send_video(update, str(file_path), t(update.effective_user.id, "pinterest_video"))
                media_type = "Pinterest видео"

            add_history(update.effective_user.id, self.url, media_type)
            return True

        except Exception as error:
            await self.handle_error(update, error, "pinterest_error", "Pinterest ERROR")
            return False

        finally:
            self.cleanup()


async def download_pinterest(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
):
    downloader = PinterestDownloader(url=url, logger=logger)
    return await downloader.download(update, context)
