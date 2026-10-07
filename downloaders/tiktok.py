import asyncio
import logging
import os
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from config import MAX_FILE_SIZE
from database.database import add_history, increase_download_count
from downloaders.base import BaseDownloader
from utils.i18n import t
from utils.media_sender import send_video
from utils.followup_media import remember_video_for_mp3
from utils.message_utils import require_effective_user
from utils.media_cache import cache_message, make_cache_key
from utils.download_limits import ensure_download_allowed

logger = logging.getLogger(__name__)


class TikTokDownloader(BaseDownloader):
    def __init__(self, url: str, logger=None, temp_root=None):
        super().__init__(url=url, logger=logger, temp_root=temp_root)

    async def download(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = require_effective_user(update)
        if not await ensure_download_allowed(update):
            return False
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

            remember_video_for_mp3(context, file_path)
            sent_message = await send_video(update, str(file_path), t(user.id, "tiktok_video"))
            cache_message(make_cache_key(self.url, "tiktok"), sent_message, "tiktok_video")

            add_history(user.id, self.url, "TikTok видео")
            increase_download_count(user.id)
            return True

        except Exception as error:
            await self.handle_error(update, error, "tiktok_error", "TikTok ERROR")
            return False

        finally:
            self.cleanup()


async def download_tiktok(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
):
    downloader = TikTokDownloader(url=url, logger=logger)
    downloader.progress_callback = context.user_data.get("download_progress_callback")
    return await downloader.download(update, context)
