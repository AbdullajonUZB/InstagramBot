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


class YoutubeDownloader(BaseDownloader):
    def __init__(self, url: str, logger=None, temp_root=None):
        super().__init__(url=url, logger=logger, temp_root=temp_root)

    async def download(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.prepare_temp_dir()

        try:
            filename = await asyncio.to_thread(
                self.download_media,
                "%(title)s.%(ext)s",
                {
                    "format": "best[ext=mp4]/best",
                    "merge_output_format": "mp4",
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

            await send_video(update, str(file_path), t(update.effective_user.id, "youtube_video"))

            add_history(update.effective_user.id, self.url, "YouTube видео")
            return True

        except Exception as error:
            await self.handle_error(update, error, "youtube_error", "YouTube ERROR")
            return False

        finally:
            self.cleanup()


async def download_youtube(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
):
    downloader = YoutubeDownloader(url=url, logger=logger)
    return await downloader.download(update, context)
