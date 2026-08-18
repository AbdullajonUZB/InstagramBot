from downloaders.instagram import download_instagram
from downloaders.youtube import download_youtube
from downloaders.tiktok import download_tiktok
from downloaders.pinterest import download_pinterest
from downloaders.facebook import download_facebook
import re
from typing import Awaitable, Callable, TypedDict


Downloader = Callable[..., Awaitable[object]]


class Service(TypedDict):
    button: str
    pattern: str
    downloader: Downloader

INSTAGRAM_PATTERN = r"(https?://(?:www\.)?instagram\.com/[^\s]+)"
YOUTUBE_PATTERN = (
    r"(https?://(?:(?:www|m)\.)?youtube\.com/"
    r"(?:watch\?v=|shorts/|live/|embed/)[^\s]+|https?://youtu\.be/[^\s]+)"
)
TIKTOK_PATTERN = r"(https?://(?:(?:www|m|vm|vt)\.)?tiktok\.com/[^\s]+)"
PINTEREST_PATTERN = r"(https?://(?:[a-z]{2}\.)?(?:pinterest\.com|pin\.it)/[^\s]+)"
FACEBOOK_PATTERN = (
    r"(https?://(?:www\.|m\.)?(?:facebook\.com|fb\.watch)/[^\s]+)"
)

SERVICES: dict[str, Service] = {
    "instagram": {
        "button": "📷 Instagram",
        "pattern": INSTAGRAM_PATTERN,
        "downloader": download_instagram,
    },
    "youtube": {
        "button": "▶️ YouTube",
        "pattern": YOUTUBE_PATTERN,
        "downloader": download_youtube,
    },
    "tiktok": {
        "button": "🎵 TikTok",
        "pattern": TIKTOK_PATTERN,
        "downloader": download_tiktok,
    },
    "pinterest": {
        "button": "📌 Pinterest",
        "pattern": PINTEREST_PATTERN,
        "downloader": download_pinterest,
    },
    "facebook": {
        "button": "📘 Facebook",
        "pattern": FACEBOOK_PATTERN,
        "downloader": download_facebook,
    },
}


def extract_service_link(text: str) -> tuple[str | None, str | None]:
    """Return (service key, URL) for the first supported link in text."""
    for key, service in SERVICES.items():
        match = re.search(service["pattern"], text)
        if match:
            url = match.group(1).rstrip(".,!?;:)]}")
            return key, url
    return None, None
