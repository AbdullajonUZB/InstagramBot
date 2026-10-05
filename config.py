import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в .env")


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} должен быть целым числом") from exc


ADMIN_IDS = {_env_int("ADMIN_ID", 136350248)}
_extra_admin_ids = os.getenv("ADMIN_IDS", "")
if _extra_admin_ids.strip():
    try:
        ADMIN_IDS.update(
            int(item.strip())
            for item in _extra_admin_ids.split(",")
            if item.strip()
        )
    except ValueError as exc:
        raise RuntimeError("ADMIN_IDS должен содержать ID через запятую") from exc

ADMIN_IDS = frozenset(ADMIN_IDS)
# Backward-compatible alias for modules that still import the singular name.
ADMIN_ID = _env_int("ADMIN_ID", 136350248)

DOWNLOAD_FOLDER = str(PROJECT_ROOT / "downloads")

MAX_FILE_SIZE = 49 * 1024 * 1024

# Telegram API network timeouts (seconds).
TELEGRAM_CONNECT_TIMEOUT = 30
TELEGRAM_READ_TIMEOUT = 30
TELEGRAM_WRITE_TIMEOUT = 60
TELEGRAM_POOL_TIMEOUT = 30
TELEGRAM_GET_UPDATES_READ_TIMEOUT = 45

MAX_MESSAGE_LENGTH = 4000
MAX_URL_LENGTH = 2000

# Telegram Mini App. The URL must be public HTTPS for Telegram clients.
WEB_APP_URL = os.getenv("WEB_APP_URL", "").strip().rstrip("/")
WEB_APP_HOST = os.getenv("WEB_APP_HOST", "127.0.0.1").strip() or "127.0.0.1"
WEB_APP_PORT = _env_int("WEB_APP_PORT", 8081)

# Настройки дружеских напоминаний неактивным пользователям.
REMINDER_AFTER_DAYS = _env_int("REMINDER_AFTER_DAYS", 7)
REMINDER_INTERVAL_HOURS = _env_int("REMINDER_INTERVAL_HOURS", 6)
REMINDER_BATCH_SIZE = _env_int("REMINDER_BATCH_SIZE", 100)

