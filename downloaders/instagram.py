import asyncio
import logging
import os
import shutil
import tempfile
from turtle import update

import yt_dlp
from yt_dlp.utils import DownloadError
from database.database import (
    add_history,
    get_user_settings,
    register_user,
    can_download,
    increase_download_count,
)
from config import MAX_FILE_SIZE
from utils.i18n import t
from utils.media_sender import send_video

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def _download_sync(ydl_opts: dict, url: str) -> str:

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:

        info = ydl.extract_info(
            url,
            download=True
        )

        return ydl.prepare_filename(info)
def _is_rate_limit(error: Exception) -> bool:
    """Проверяет, связана ли ошибка с ограничением Instagram."""
    text = str(error).lower()

    return (
        "429" in text
        or "too many requests" in text
        or "rate limit" in text
    )

async def download_instagram(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
):
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

    temp_dir = tempfile.mkdtemp(prefix="instagram_")

    output = os.path.join(
        temp_dir,
        "%(title)s.%(ext)s"
    )

    ydl_opts = {
    "outtmpl": output,

    "quiet": True,
    "no_warnings": True,

    "cookiefile": "cookies.txt",

    "noplaylist": True,

    "merge_output_format": "mp4",

    "retries": 10,

    "fragment_retries": 10,

    "socket_timeout": 60,

    "http_headers": {
        "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0 Safari/537.36",

        "Accept-Language": "en-US,en;q=0.9",
    },
}

    try:
        
        filename = await asyncio.to_thread(
        _download_sync,
        ydl_opts,
        url
        )

        
        if not os.path.exists(filename):

            for file in os.listdir(temp_dir):

                path = os.path.join(
                    temp_dir,
                    file
                )

                if os.path.isfile(path):

                    filename = path
                    break

        if not os.path.exists(filename):

            await update.message.reply_text(
                t(update.effective_user.id, "file_missing")
            )

            shutil.rmtree(
                temp_dir,
                ignore_errors=True
            )

            return True

        extension = os.path.splitext(
                filename
            )[1].lower()

        image_formats = [
                ".jpg",
                ".jpeg",
                ".png",
                ".webp"
            ]

        video_formats = [
                ".mp4",
                ".mov",
                ".mkv",
                ".webm"
            ]

        if extension in image_formats:

                with open(filename, "rb") as photo:

                    await update.message.reply_photo(
                        photo=photo,
                        caption=t(update.effective_user.id, "instagram_photo")
                    )
                    add_history(
                        update.effective_user.id,
                        url,
                        "Фото"
                    )
                    increase_download_count(update.effective_user.id)
                    shutil.rmtree(
                        temp_dir,
                        ignore_errors=True
                )
                return True
        elif extension in video_formats:

                size = os.path.getsize(filename)

                if size > MAX_FILE_SIZE:

                    await update.message.reply_text(
                        t(update.effective_user.id, "file_too_large")
                    )

                    shutil.rmtree(
                        temp_dir,
                        ignore_errors=True
                    )

                    return False

                await send_video(
                    update,
                    filename,
                    t(update.effective_user.id, "instagram_video"),
                )
                add_history(
                    update.effective_user.id,
                    url,
                    "Видео"
                )
                
                increase_download_count(update.effective_user.id)
                
                shutil.rmtree(
                    temp_dir,
                    ignore_errors=True
                )
                return True
        else:

                with open(filename, "rb") as document:

                    await update.message.reply_document(
                        document=document,
                        caption=t(update.effective_user.id, "instagram_document")
                    )
                    add_history(
                        update.effective_user.id,
                        url,
                        "Документ"
                    )
                    increase_download_count(update.effective_user.id)

                    shutil.rmtree(
                        temp_dir,
                        ignore_errors=True
                    )
                    return True

    except Exception as e:

        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )

        logger.error("Instagram ERROR: %s", e, exc_info=True)

        await update.message.reply_text(
            t(update.effective_user.id, "instagram_error")
        )

        return False