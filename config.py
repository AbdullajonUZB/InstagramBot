import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

DOWNLOAD_FOLDER = "downloads"

MAX_FILE_SIZE = 49 * 1024 * 1024

# Telegram API network timeouts (seconds).
TELEGRAM_CONNECT_TIMEOUT = 30
TELEGRAM_READ_TIMEOUT = 30
TELEGRAM_WRITE_TIMEOUT = 60
TELEGRAM_POOL_TIMEOUT = 30
TELEGRAM_GET_UPDATES_READ_TIMEOUT = 45

# Администратор
ADMIN_ID = 136350248
