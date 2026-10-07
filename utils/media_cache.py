from urllib.parse import urlsplit, urlunsplit

from database.database import get_cached_media, save_cached_media
from utils.download_audit import audit_successful_download
from utils.i18n import t
from utils.message_utils import require_effective_user, require_message_target


def make_cache_key(url: str, variant: str = "default") -> str:
    parsed = urlsplit(url.strip())
    canonical = urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), parsed.query, ""))
    return f"{canonical}|{variant}"


def cache_message(cache_key: str, sent_message, caption_key: str):
    if sent_message is None:
        return
    for media_type in ("video", "photo", "document", "audio"):
        media = getattr(sent_message, media_type, None)
        if media is not None and getattr(media, "file_id", None):
            save_cached_media(cache_key, media_type, media.file_id, caption_key)
            return


async def send_cached_media(update, cache_key: str, context=None):
    cached = get_cached_media(cache_key)
    if not cached:
        return None
    media_type, file_id, caption_key = cached
    message = require_message_target(update)
    user_id = require_effective_user(update).id
    caption = t(user_id, caption_key) if caption_key else None
    sender = getattr(message, f"reply_{media_type}", None)
    if sender is None:
        return None
    kwargs = {media_type: file_id}
    if caption:
        kwargs["caption"] = caption
    if media_type == "video":
        kwargs["supports_streaming"] = True
    sent_message = await sender(**kwargs)
    if context is not None:
        variant = cache_key.rsplit("|", 1)[-1]
        service = variant.split(":", 1)[0]
        label = {
            "youtube": "YouTube аудио" if ":audio" in variant else "YouTube видео",
            "instagram": "Instagram медиа",
            "facebook": "Facebook медиа",
            "pinterest": "Pinterest медиа",
        }.get(service, service)
        await audit_successful_download(
            context,
            update,
            cache_key.rsplit("|", 1)[0],
            f"{label} (из кэша)",
            sent_message,
        )
    return sent_message
