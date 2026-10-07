"""Return direct MP4 streams as inline video results when a site allows it."""

import asyncio
import hashlib
import logging
from pathlib import Path
from urllib.parse import urlsplit

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InlineQueryResultVideo,
    InlineQueryResultsButton,
    InputTextMessageContent,
)
from telegram.ext import ContextTypes
from yt_dlp import YoutubeDL

from config import MAX_FILE_SIZE
from database.database import consume_inline_trial
from downloaders.instagram import is_instagram_story_profile_url, is_instagram_story_url
from downloaders.youtube import _youtube_runtime_options
from services import SERVICES, extract_service_link


logger = logging.getLogger(__name__)
INLINE_QUERY_MAX_LENGTH = 2000
INLINE_TRIAL_LIMIT = 3
INLINE_METADATA_TIMEOUT = 6
INLINE_DEBOUNCE_SECONDS = 0.35


def build_inline_result(service_key: str, url: str, bot_username: str):
    service = SERVICES[service_key]
    service_name = service["button"].split(" ", 1)[-1]
    result_id = hashlib.sha256(f"{service_key}:{url}".encode("utf-8")).hexdigest()[:32]
    return InlineQueryResultArticle(
        id=result_id,
        title=f"📥 Ссылка из {service_name}",
        description="Отправить ссылку в чат; для скачивания откройте бота",
        input_message_content=InputTextMessageContent(
            message_text=(
                f"📥 Ссылка на публикацию ({service_name}):\n{url}\n\n"
                "Чтобы скачать, откройте бота и отправьте ему эту ссылку."
            )
        ),
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("📥 Открыть бота", url=f"https://t.me/{bot_username}")]]
        ),
    )


def _inline_ydl_options(service_key: str) -> dict:
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "socket_timeout": 4,
        "retries": 0,
        "extractor_retries": 0,
        "format": "best[ext=mp4][vcodec!=none][acodec!=none]/b[ext=mp4]/best[ext=mp4]",
    }
    if service_key == "youtube":
        options.update(_youtube_runtime_options())
        options["format"] = "18/best[ext=mp4][vcodec!=none][acodec!=none]/best[ext=mp4]"
    elif service_key == "instagram":
        options.update(
            {
                "cookiefile": str(Path(__file__).resolve().parent.parent / "cookies.txt"),
                "format": "b[ext=mp4]/best[ext=mp4]",
                "http_headers": {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/138.0 Safari/537.36"
                    ),
                    "Accept-Language": "en-US,en;q=0.9",
                },
            }
        )
    elif service_key == "facebook":
        options["format"] = "b[ext=mp4][height<=720]/b[ext=mp4]"
    return options


def _find_direct_video(info: dict | None) -> dict | None:
    if not info:
        return None
    entries = list(info.get("entries") or [info])
    for entry in entries:
        if not entry:
            continue
        candidates = list(entry.get("formats") or [])
        if entry.get("url"):
            candidates.append(entry)
        direct = []
        for media_format in candidates:
            media_url = media_format.get("url")
            parsed = urlsplit(media_url or "")
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                continue
            if media_format.get("ext") != "mp4":
                continue
            if media_format.get("vcodec") in {None, "none"}:
                continue
            if media_format.get("acodec") in {None, "none"}:
                continue
            height = media_format.get("height")
            if height and height > 720:
                continue
            size = media_format.get("filesize") or media_format.get("filesize_approx")
            if size and size > MAX_FILE_SIZE:
                continue
            direct.append(media_format)
        if direct:
            selected = max(
                direct,
                key=lambda item: (
                    1 if (item.get("height") or 0) <= 720 else 0,
                    item.get("height") or 0,
                    item.get("tbr") or 0,
                ),
            )
            thumbnail = entry.get("thumbnail") or info.get("thumbnail")
            if not thumbnail:
                thumbnails = entry.get("thumbnails") or info.get("thumbnails") or []
                available = [item for item in thumbnails if item.get("url")]
                if available:
                    thumbnail = max(
                        available,
                        key=lambda item: (item.get("width") or 0) * (item.get("height") or 0),
                    )["url"]
            return {
                **selected,
                "title": entry.get("title") or info.get("title"),
                "thumbnail": thumbnail,
            }
    return None


def extract_direct_video(service_key: str, url: str) -> dict | None:
    """Extract a Telegram-fetchable MP4 URL without downloading the media locally."""
    try:
        with YoutubeDL(_inline_ydl_options(service_key)) as ydl:
            info = ydl.extract_info(url, download=False)
        return _find_direct_video(info)
    except Exception as error:
        logger.info("Inline direct stream unavailable for %s: %s", service_key, error)
        return None


def build_video_result(service_key: str, url: str, video: dict, used: int, bot_username: str):
    service_name = SERVICES[service_key]["button"].split(" ", 1)[-1]
    result_id = hashlib.sha256(f"inline:{service_key}:{url}".encode("utf-8")).hexdigest()[:32]
    thumbnail = video.get("thumbnail")
    if urlsplit(thumbnail or "").scheme not in {"http", "https"}:
        return None
    return InlineQueryResultVideo(
        id=result_id,
        video_url=video["url"],
        mime_type="video/mp4",
        thumbnail_url=thumbnail,
        title=(video.get("title") or f"Видео из {service_name}")[:64],
        description=f"Пробный результат {used}/{INLINE_TRIAL_LIMIT}",
        caption=f"📥 Видео из {service_name} · пробный результат {used}/{INLINE_TRIAL_LIMIT}",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("📥 Открыть бота", url=f"https://t.me/{bot_username}")]]
        ),
    )


def build_trial_over_result(bot_username: str):
    return InlineQueryResultsButton(
        text="📥 Продолжить в личном чате",
        start_parameter="inline",
    )


async def handle_inline_query(update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query
    user = update.effective_user
    if query is None or user is None:
        return

    # Inline clients update the query while each character is typed. Debounce
    # these updates so one pasted URL starts only one metadata request.
    data = context.application.bot_data
    latest = data.setdefault("inline_latest_query", {})
    latest[user.id] = query.id
    await asyncio.sleep(INLINE_DEBOUNCE_SECONDS)
    if latest.get(user.id) != query.id:
        await query.answer([], cache_time=0, is_personal=True)
        return

    text = (query.query or "").strip()
    if len(text) > INLINE_QUERY_MAX_LENGTH:
        await query.answer([], cache_time=0, is_personal=True)
        return

    service_key, url = extract_service_link(text)
    if not service_key or not url:
        await query.answer([], cache_time=0, is_personal=True)
        return

    if service_key == "instagram" and (
        is_instagram_story_url(url) or is_instagram_story_profile_url(url)
    ):
        await query.answer([], cache_time=0, is_personal=True)
        return

    video_cache = data.setdefault("inline_video_cache", {})
    used_before = video_cache.get(url)
    if used_before and used_before[0] > asyncio.get_running_loop().time():
        video = used_before[1]
    else:
        semaphore = data.setdefault("inline_extract_semaphore", asyncio.Semaphore(2))
        extract_tasks = data.setdefault("inline_extract_tasks", {})
        task = extract_tasks.get(url)
        if task is None or task.done():
            async def guarded_extract():
                async with semaphore:
                    return await asyncio.to_thread(extract_direct_video, service_key, url)

            task = asyncio.create_task(guarded_extract())
            extract_tasks[url] = task

            def cache_finished(done_task):
                extract_tasks.pop(url, None)
                try:
                    extracted = done_task.result()
                except Exception:
                    logger.exception("Inline metadata task failed for %s", service_key)
                    return
                if extracted:
                    video_cache[url] = (asyncio.get_running_loop().time() + 20, extracted)

            task.add_done_callback(cache_finished)
        try:
            video = await asyncio.wait_for(
                asyncio.shield(task), timeout=INLINE_METADATA_TIMEOUT
            )
        except asyncio.TimeoutError:
            video = None

    bot = await context.bot.get_me()
    if not bot.username:
        await query.answer([], cache_time=0, is_personal=True)
        return

    if not video:
        await query.answer(
            [build_inline_result(service_key, url, bot.username)],
            cache_time=0,
            is_personal=True,
            button=InlineQueryResultsButton(
                text="📥 Открыть бота для надёжного скачивания",
                start_parameter="inline",
            ),
        )
        return

    if not video.get("thumbnail"):
        await query.answer(
            [build_inline_result(service_key, url, bot.username)],
            cache_time=0,
            is_personal=True,
        )
        return

    allowed, used = await asyncio.to_thread(
        consume_inline_trial,
        user.id,
        query.id,
        INLINE_TRIAL_LIMIT,
    )
    if not allowed:
        await query.answer(
            [],
            cache_time=0,
            is_personal=True,
            button=build_trial_over_result(bot.username),
        )
        return

    result = build_video_result(service_key, url, video, used, bot.username)
    if result is None:
        await query.answer(
            [build_inline_result(service_key, url, bot.username)],
            cache_time=0,
            is_personal=True,
            button=InlineQueryResultsButton(
                text="📥 Открыть бота для надёжного скачивания",
                start_parameter="inline",
            ),
        )
        return

    await query.answer([result], cache_time=0, is_personal=True)
