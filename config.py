import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

DOWNLOAD_FOLDER = "downloads"

MAX_FILE_SIZE = 49 * 1024 * 1024

# Администратор
ADMIN_ID = 136350248