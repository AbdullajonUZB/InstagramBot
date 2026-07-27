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


class TikTokDownloader(BaseDownloader):
    def __init__(self, url: str, logger=None, temp_root=None):
        super().__init__(url=url, logger=logger, temp_root=temp_root)

    async def download(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.prepare_temp_dir()

        try:
            filename = await asyncio.to_thread(
                self.download_media,
                "%(title)s.%(ext)s",
                {
                    "merge_output_format": "mp4",
                    "max_filesize": MAX_FILE_SIZE,
                },
            )

            file_path = Path(filename)
            if not file_path.exists():
                files = [path for path in self.temp_dir.iterdir() if path.is_file()]
                file_path = files[0] if files else None

            if not file_path or not file_path.exists():
                await update.message.reply_text(t(update.effective_user.id, "file_missing"))
                return False

            try:
                self.validate_file(file_path, max_size=MAX_FILE_SIZE)
            except FileNotFoundError:
                await update.message.reply_text(t(update.effective_user.id, "file_missing"))
                return False
            except ValueError as error:
                if "exceeds maximum size" in str(error):
                    await update.message.reply_text(t(update.effective_user.id, "file_too_large"))
                    return False
                if "empty" in str(error):
                    await update.message.reply_text(t(update.effective_user.id, "file_missing"))
                    return False
                raise

            await send_video(update, str(file_path), t(update.effective_user.id, "tiktok_video"))

            add_history(update.effective_user.id, self.url, "TikTok видео")
            return True

        except Exception as error:
            logger.error("TikTok ERROR: %s", error, exc_info=True)

            await update.message.reply_text(t(update.effective_user.id, "tiktok_error"))
            return False

        finally:
            self.cleanup()


async def download_tiktok(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
):
    downloader = TikTokDownloader(url=url, logger=logger)
    return await downloader.download(update, context)
