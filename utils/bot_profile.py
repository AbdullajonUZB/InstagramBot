"""Static profile text shown even while the home-hosted bot is offline."""

import logging

logger = logging.getLogger(__name__)

BOT_PROFILE_TEXT = {
    "": (
        "Media Downloader: фото и видео из Instagram, YouTube, Pinterest и Facebook; "
        "YouTube MP3. Обычно онлайн ежедневно 08:00–00:00 по Ташкенту (16 часов). "
        "Работает на домашнем компьютере, поэтому ночью и во время обновлений недоступен. "
        "Скачивание зависит от доступности публикации и ограничений платформ."
    ),
    "ru": (
        "Media Downloader: фото и видео из Instagram, YouTube, Pinterest и Facebook; "
        "YouTube MP3. Обычно онлайн ежедневно 08:00–00:00 по Ташкенту (16 часов). "
        "Работает на домашнем компьютере, поэтому ночью и во время обновлений недоступен. "
        "Скачивание зависит от доступности публикации и ограничений платформ."
    ),
    "uz": (
        "Media Downloader: Instagram, YouTube, Pinterest va Facebook’dan foto va videolar, "
        "YouTube’dan MP3. Har kuni Toshkent vaqti bilan 08:00–00:00 da ishlaydi (16 soat). "
        "Uy kompyuterida ishlaydi, tunda va yangilanish vaqtida mavjud emas. "
        "Yuklab olish platforma cheklovlariga bog‘liq."
    ),
    "en": (
        "Media Downloader: photos and videos from Instagram, YouTube, Pinterest and Facebook; "
        "YouTube MP3. Usually online daily, 08:00–00:00 Tashkent time (16 hours). "
        "Runs on a home computer and is offline overnight and during updates. "
        "Downloads depend on platform availability and restrictions."
    ),
}

BOT_SHORT_PROFILE_TEXT = {
    "": "Фото/видео из соцсетей и YouTube MP3. Обычно онлайн 08:00–00:00 по Ташкенту (16/7); домашний ПК.",
    "ru": "Фото/видео из соцсетей и YouTube MP3. Обычно онлайн 08:00–00:00 по Ташкенту (16/7); домашний ПК.",
    "uz": "Ijtimoiy tarmoq foto/video va YouTube MP3. Har kuni 08:00–00:00, Toshkent vaqti (16/7); uy kompyuteri.",
    "en": "Social media photo/video and YouTube MP3. Usually online 08:00–00:00 Tashkent time (16/7); home PC.",
}


async def configure_bot_profile(bot):
    """Set fallback and localized descriptions; failures must not block startup."""
    for language, description in BOT_PROFILE_TEXT.items():
        try:
            await bot.set_my_description(description=description, language_code=language)
        except Exception:
            logger.warning("Не удалось обновить описание бота для языка %s", language or "по умолчанию")
            continue
    for language, description in BOT_SHORT_PROFILE_TEXT.items():
        try:
            await bot.set_my_short_description(short_description=description, language_code=language)
        except Exception:
            logger.warning("Не удалось обновить короткое описание бота для языка %s", language or "по умолчанию")
            continue


def format_uptime(seconds: float | int | None) -> str:
    if seconds is None:
        return "неизвестно"
    total = max(0, int(seconds))
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    if days:
        return f"{days} дн. {hours} ч. {minutes} мин."
    if hours:
        return f"{hours} ч. {minutes} мин."
    return f"{minutes} мин."
