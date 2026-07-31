from telegram.error import TimedOut

from database.database import get_user_settings
from utils.message_utils import get_message_target


async def send_video(update, filename, video_caption, document_caption=None):
    with open(filename, "rb") as media:

        settings = get_user_settings(update.effective_user.id)
        message = get_message_target(update)

        # Отправка как документ
        if settings["send_format"] == "document":

            for attempt in range(3):
                try:
                    await message.reply_document(
                        document=media,
                        caption=document_caption or video_caption,
                        read_timeout=600,
                        write_timeout=600,
                        connect_timeout=60,
                        pool_timeout=60,
                    )
                    return

                except TimedOut:

                    if attempt == 2:
                        raise

                    media.seek(0)

        # Отправка как видео
        else:

            for attempt in range(3):
                try:
                    await message.reply_video(
                        video=media,
                        caption=video_caption,
                        supports_streaming=True,
                        read_timeout=600,
                        write_timeout=600,
                        connect_timeout=60,
                        pool_timeout=60,
                    )
                    return

                except TimedOut:

                    if attempt == 2:
                        raise

                    media.seek(0)