"""Mirror successful user downloads to the private administrator archive."""

import logging
from datetime import datetime, timedelta, timezone

from telegram import InputMediaPhoto, InputMediaVideo

from config import INLINE_CACHE_CHAT_ID


logger = logging.getLogger(__name__)
TASHKENT = timezone(timedelta(hours=5), name="Asia/Tashkent")


def _get_media(message):
    for attribute in ("video", "photo", "audio", "document", "animation", "voice"):
        media = getattr(message, attribute, None)
        if media:
            if attribute == "photo":
                media = media[-1]
            return attribute, media.file_id
    return None


def _audit_text(user, service, url):
    username = f"@{user.username}" if user.username else "не указан"
    first_name = user.full_name or user.first_name or "Без имени"
    timestamp = datetime.now(TASHKENT).strftime("%d.%m.%Y %H:%M:%S")
    text = (
        f"📥 {service}\n"
        f"👤 {first_name} ({username})\n"
        f"🆔 Telegram ID: {user.id}\n"
        f"🔗 {url}\n"
        f"🕒 {timestamp} (Ташкент)"
    )
    return text if len(text) <= 1024 else f"{text[:1023]}…"


async def audit_successful_download(context, update, url: str, service: str, messages):
    """Copy a successful result plus its attribution to the private cache channel."""
    if not INLINE_CACHE_CHAT_ID:
        return
    user = getattr(update, "effective_user", None)
    if user is None:
        return

    if not isinstance(messages, (list, tuple)):
        messages = [messages]
    media = [_get_media(message) for message in messages if message is not None]
    media = [item for item in media if item]
    if not media:
        return

    try:
        caption = _audit_text(user, service, url)
        if len(media) > 1 and all(kind in {"photo", "video"} for kind, _ in media):
            for start in range(0, len(media), 10):
                group = media[start:start + 10]
                input_media = []
                for index, (kind, file_id) in enumerate(group):
                    item_caption = caption if start == 0 and index == 0 else None
                    if kind == "video":
                        input_media.append(InputMediaVideo(
                            file_id,
                            supports_streaming=True,
                            caption=item_caption,
                        ))
                    else:
                        input_media.append(InputMediaPhoto(file_id, caption=item_caption))
                await context.bot.send_media_group(
                    chat_id=INLINE_CACHE_CHAT_ID,
                    media=input_media,
                )
            return

        for kind, file_id in media:
            if kind == "photo":
                await context.bot.send_photo(
                    chat_id=INLINE_CACHE_CHAT_ID,
                    photo=file_id,
                    caption=caption,
                )
            elif kind == "video":
                await context.bot.send_video(
                    chat_id=INLINE_CACHE_CHAT_ID,
                    video=file_id,
                    supports_streaming=True,
                    caption=caption,
                )
            elif kind == "audio":
                await context.bot.send_audio(
                    chat_id=INLINE_CACHE_CHAT_ID,
                    audio=file_id,
                    caption=caption,
                )
            elif kind == "document":
                await context.bot.send_document(
                    chat_id=INLINE_CACHE_CHAT_ID,
                    document=file_id,
                    caption=caption,
                )
            elif kind == "animation":
                await context.bot.send_animation(
                    chat_id=INLINE_CACHE_CHAT_ID,
                    animation=file_id,
                    caption=caption,
                )
            elif kind == "voice":
                await context.bot.send_voice(
                    chat_id=INLINE_CACHE_CHAT_ID,
                    voice=file_id,
                    caption=caption,
                )
    except Exception:
        logger.exception("Could not archive successful download for user %s", user.id)
