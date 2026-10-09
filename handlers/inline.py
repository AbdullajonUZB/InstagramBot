"""Return direct MP4 streams as inline video results when a site allows it."""

import asyncio
import hashlib
import logging
import shutil
import tempfile
from pathlib import Path
from collections.abc import Mapping
from typing import Any, cast
from urllib.parse import urlsplit

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InlineQueryResultCachedVideo,
    InlineQueryResultVideo,
    InlineQueryResultsButton,
    InputTextMessageContent,
)
from telegram.ext import ContextTypes
from yt_dlp import YoutubeDL

from config import INLINE_CACHE_CHAT_ID, MAX_FILE_SIZE
from database.database import (
    consume_inline_trial,
    get_cached_media,
    get_inline_trial_count,
    save_cached_media,
)
from downloaders.base import VIDEO_EXTENSIONS
from downloaders.facebook import FACEBOOK_FORMAT, FacebookDownloader
from downloaders.instagram import (
    InstagramDownloader,
    is_instagram_story_profile_url,
    is_instagram_story_url,
)
from downloaders.pinterest import PinterestDownloader
from downloaders.youtube import YoutubeDownloader, _youtube_runtime_options
from services import SERVICES, extract_service_link
from utils.media_cache import make_cache_key
from utils.video_compat import ensure_telegram_compatible_video


logger = logging.getLogger(__name__)
INLINE_QUERY_MAX_LENGTH = 2000
INLINE_TRIAL_LIMIT = 3
INLINE_METADATA_TIMEOUT = 6
INLINE_DEBOUNCE_SECONDS = 0.35
INLINE_CACHE_VARIANT = "inline:video"


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


def _find_direct_video(info: Mapping[str, Any] | None) -> dict | None:
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
            protocol = media_format.get("protocol")
            if protocol and protocol not in {"http", "https"}:
                continue
            if media_format.get("ext") != "mp4":
                continue
            if media_format.get("vcodec") in {None, "none"}:
                continue
            if media_format.get("acodec") in {None, "none"}:
                continue
            required_headers = {
                header.lower()
                for header in (media_format.get("http_headers") or {})
                if header.lower() in {"cookie", "authorization", "referer", "origin"}
            }
            if required_headers:
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
        with YoutubeDL(cast(Any, _inline_ydl_options(service_key))) as ydl:
            info = ydl.extract_info(url, download=False)
        return _find_direct_video(info)
    except Exception as error:
        logger.info("Inline direct stream unavailable for %s: %s", service_key, error)
        return None


def _cache_download_options(service_key: str, downloader) -> dict:
    if service_key == "youtube":
        options: dict[str, Any] = downloader._build_video_options("auto")
    elif service_key == "instagram":
        options = _inline_ydl_options(service_key)
        options.update(
            {
                "format": (
                    "bv*[ext=mp4][vcodec^=avc]+ba[ext=m4a]/"
                    "b[ext=mp4]/bv*+ba/b"
                ),
                "retries": 3,
                "fragment_retries": 3,
                "extractor_retries": 2,
                "socket_timeout": 15,
            }
        )
    elif service_key == "facebook":
        options = {"format": FACEBOOK_FORMAT, "merge_output_format": "mp4"}
    else:
        options = {"max_filesize": MAX_FILE_SIZE}
    options.pop("skip_download", None)
    options.update({"max_filesize": MAX_FILE_SIZE, "noplaylist": True})
    return options


def _make_cache_downloader(service_key: str, url: str, temp_root: Path):
    downloader_type = {
        "youtube": YoutubeDownloader,
        "instagram": InstagramDownloader,
        "facebook": FacebookDownloader,
        "pinterest": PinterestDownloader,
    }[service_key]
    return downloader_type(url=url, temp_root=temp_root)


async def _prepare_video_in_cache_channel(service_key: str, url: str, context, cache_key: str):
    """Download a fallback copy and store its Telegram file_id in a private channel."""
    task_map = context.application.bot_data.setdefault("inline_prepare_tasks", {})
    temp_root = Path(tempfile.mkdtemp(prefix="inline_video_cache_"))
    downloader = _make_cache_downloader(service_key, url, temp_root)
    try:
        downloader.prepare_temp_dir()
        options = _cache_download_options(service_key, downloader)
        filename = await asyncio.to_thread(
            downloader.download_media,
            "inline_%(id)s.%(ext)s",
            options,
        )
        file_path = downloader.resolve_downloaded_file(filename)
        if file_path is None or file_path.suffix.lower() not in VIDEO_EXTENSIONS:
            file_path = next(
                (
                    item for item in downloader.get_downloaded_media_files()
                    if item.suffix.lower() in VIDEO_EXTENSIONS
                ),
                None,
            )
        if file_path is None or not file_path.exists():
            raise RuntimeError("Источник не вернул готовый видеофайл")
        if file_path.stat().st_size > MAX_FILE_SIZE:
            raise ValueError("Видео больше допустимого размера для пробной inline-отправки")

        file_path = await ensure_telegram_compatible_video(file_path)
        if file_path.stat().st_size > MAX_FILE_SIZE:
            raise ValueError("Подготовленное видео превышает лимит размера")

        with file_path.open("rb") as video_file:
            stored = await context.bot.send_video(
                chat_id=INLINE_CACHE_CHAT_ID,
                video=video_file,
                supports_streaming=True,
                disable_notification=True,
                read_timeout=180,
                write_timeout=180,
                connect_timeout=30,
                pool_timeout=30,
            )
        if not stored.video or not stored.video.file_id:
            raise RuntimeError("Telegram не вернул file_id сохранённого видео")
        await asyncio.to_thread(
            save_cached_media,
            cache_key,
            "video",
            stored.video.file_id,
            "",
        )
        logger.info("Prepared inline video cache entry for %s", service_key)
    except Exception:
        logger.exception("Could not prepare inline video fallback for %s", service_key)
    finally:
        downloader.cleanup()
        shutil.rmtree(temp_root, ignore_errors=True)
        task_map.pop(cache_key, None)


def build_preparing_result(service_key: str, url: str, bot_username: str):
    service_name = SERVICES[service_key]["button"].split(" ", 1)[-1]
    result_id = hashlib.sha256(f"prepare:{service_key}:{url}".encode("utf-8")).hexdigest()[:32]
    return InlineQueryResultArticle(
        id=result_id,
        title="⏳ Видео готовится",
        description="Через несколько секунд повторите тот же запрос",
        input_message_content=InputTextMessageContent(
            message_text=(
                f"⏳ Готовим видео из {service_name}.\n"
                f"Через несколько секунд повторите запрос @{bot_username} со ссылкой, "
                "чтобы отправить видео прямо в чат."
            )
        ),
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("📥 Открыть бота", url=f"https://t.me/{bot_username}")]]
        ),
    )


def build_video_result(service_key: str, url: str, video: dict, used: int, bot_username: str):
    service_name = SERVICES[service_key]["button"].split(" ", 1)[-1]
    result_id = hashlib.sha256(f"inline:{service_key}:{url}".encode("utf-8")).hexdigest()[:32]
    thumbnail = video.get("thumbnail")
    if not isinstance(thumbnail, str) or urlsplit(thumbnail).scheme not in {"http", "https"}:
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


def build_cached_video_result(service_key: str, url: str, file_id: str, used: int, bot_username: str):
    service_name = SERVICES[service_key]["button"].split(" ", 1)[-1]
    result_id = hashlib.sha256(f"cached:{service_key}:{url}".encode("utf-8")).hexdigest()[:32]
    return InlineQueryResultCachedVideo(
        id=result_id,
        video_file_id=file_id,
        title=f"Видео из {service_name}",
        description=f"Пробный результат {used}/{INLINE_TRIAL_LIMIT}",
        caption=f"📥 Видео из {service_name} · пробный результат {used}/{INLINE_TRIAL_LIMIT}",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("📥 Открыть бота", url=f"https://t.me/{bot_username}")]]
        ),
    )


def build_trial_over_result():
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

    used_count = await asyncio.to_thread(get_inline_trial_count, user.id)
    if used_count >= INLINE_TRIAL_LIMIT:
        await query.answer(
            [],
            cache_time=0,
            is_personal=True,
            button=build_trial_over_result(),
        )
        return

    bot = await context.bot.get_me()
    if not bot.username:
        await query.answer([], cache_time=0, is_personal=True)
        return

    cache_key = make_cache_key(url, INLINE_CACHE_VARIANT)
    cached_media = await asyncio.to_thread(get_cached_media, cache_key)
    if cached_media and cached_media[0] == "video":
        allowed, used = await asyncio.to_thread(
            consume_inline_trial, user.id, query.id, INLINE_TRIAL_LIMIT
        )
        if not allowed:
            await query.answer(
                [], cache_time=0, is_personal=True,
                button=build_trial_over_result(),
            )
            return
        await query.answer(
            [build_cached_video_result(service_key, url, cached_media[1], used, bot.username)],
            cache_time=0,
            is_personal=True,
        )
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

            task = context.application.create_task(guarded_extract())
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

    if not video:
        if INLINE_CACHE_CHAT_ID is not None:
            prep_tasks = data.setdefault("inline_prepare_tasks", {})
            if cache_key not in prep_tasks or prep_tasks[cache_key].done():
                prep_tasks[cache_key] = context.application.create_task(
                    _prepare_video_in_cache_channel(service_key, url, context, cache_key)
                )
            await query.answer(
                [build_preparing_result(service_key, url, bot.username)],
                cache_time=0,
                is_personal=True,
            )
        else:
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

    if urlsplit(video.get("thumbnail") or "").scheme not in {"http", "https"}:
        if INLINE_CACHE_CHAT_ID is not None:
            prep_tasks = data.setdefault("inline_prepare_tasks", {})
            if cache_key not in prep_tasks or prep_tasks[cache_key].done():
                prep_tasks[cache_key] = context.application.create_task(
                    _prepare_video_in_cache_channel(service_key, url, context, cache_key)
                )
            await query.answer(
                [build_preparing_result(service_key, url, bot.username)],
                cache_time=0,
                is_personal=True,
            )
        else:
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
            button=build_trial_over_result(),
        )
        return

    result = build_video_result(service_key, url, video, used, bot.username)
    if result is None:
        # Without an accessible thumbnail Telegram cannot show a video result.
        # Do not charge the trial for a fallback link card.
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
