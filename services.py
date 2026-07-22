from downloaders.instagram import download_instagram
from downloaders.youtube import download_youtube
from downloaders.tiktok import download_tiktok
from downloaders.pinterest import download_pinterest
from downloaders.facebook import download_facebook

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

SERVICES = {
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