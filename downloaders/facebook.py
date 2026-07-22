import asyncio
import logging
import os
import shutil
import tempfile
import traceback

import yt_dlp
from telegram import Update
from telegram.ext import ContextTypes

from config import MAX_FILE_SIZE
from database.database import add_history
from utils.i18n import t
from utils.media_sender import send_video

logger = logging.getLogger(__name__)


def _download_sync(ydl_opts: dict, url: str):
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        logger.debug("%s", info)
        return ydl.prepare_filename(info)


async def download_facebook(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
):
    print("========== FACEBOOK.PY LOADED ==========")
    
    temp_dir = tempfile.mkdtemp(prefix="facebook_")
    output = os.path.join(temp_dir, "%(title)s.%(ext)s")

    ydl_opts = {
        "outtmpl": output,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "max_filesize": MAX_FILE_SIZE,
    }

    try:
        print("1. Начали скачивание")
        filename = await asyncio.to_thread(_download_sync, ydl_opts, url)
        print("2. filename =", filename)
        
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

        extension = os.path.splitext(filename)[1].lower()
        print("3. extension =", extension)
        if extension in {".jpg", ".jpeg", ".png", ".webp"}:
            with open(filename, "rb") as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=t(update.effective_user.id, "facebook_photo"),
                )
            media_type = "Facebook фото"
        else:
            await send_video(
                update,
                filename,
                t(update.effective_user.id, "facebook_video"),
            )
            media_type = "Facebook видео"

        add_history(update.effective_user.id, url, media_type)
        print("4. Готово")
        return True

    except Exception as error:
        import traceback
        traceback.print_exc()
        
        logger.error("Facebook ERROR: %s", error, exc_info=True)

        await update.message.reply_text(
            t(update.effective_user.id, "facebook_error")
        )
        return False

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)