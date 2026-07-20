import asyncio
import logging
import os
import shutil
import tempfile

import yt_dlp
from telegram import Update
from telegram.ext import ContextTypes

from config import MAX_FILE_SIZE
from database.database import add_history
from utils.i18n import t
from utils.media_sender import send_video

logger = logging.getLogger(__name__)


def _download_sync(ydl_opts: dict, url: str) -> str:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)


async def download_tiktok(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
):
    temp_dir = tempfile.mkdtemp(prefix="tiktok_")
    output = os.path.join(temp_dir, "%(title)s.%(ext)s")

    ydl_opts = {
        "outtmpl": output,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "merge_output_format": "mp4",
        "max_filesize": MAX_FILE_SIZE,
    }

    try:
        filename = await asyncio.to_thread(_download_sync, ydl_opts, url)

        if not os.path.exists(filename):
            files = [
                os.path.join(temp_dir, file)
                for file in os.listdir(temp_dir)
                if os.path.isfile(os.path.join(temp_dir, file))
            ]
            filename = files[0] if files else None

        if not filename or not os.path.exists(filename):
            await update.message.reply_text(t(update.effective_user.id, "file_missing"))
            return False

        if os.path.getsize(filename) > MAX_FILE_SIZE:
            await update.message.reply_text(t(update.effective_user.id, "file_too_large"))
            return False

        await send_video(update, filename, t(update.effective_user.id, "tiktok_video"))

        add_history(update.effective_user.id, url, "TikTok видео")
        return True

    except Exception as error:
        logger.error("TikTok ERROR: %s", error, exc_info=True)

        await update.message.reply_text(
            t(update.effective_user.id, "tiktok_error")
        )
        return False

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
