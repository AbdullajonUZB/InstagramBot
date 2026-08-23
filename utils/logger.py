import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        RotatingFileHandler(
            LOG_DIR / "bot.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        ),
        logging.StreamHandler()
    ]
)

# HTTP request logs may contain bot API URLs. Keep them out of normal logs.
for noisy_logger in ("httpx", "httpcore"):
    logging.getLogger(noisy_logger).setLevel(logging.WARNING)

# python-telegram-bot retries transient polling failures internally. Avoid
# printing a full traceback for every temporary connection reset.
logging.getLogger("telegram.ext._utils.networkloop").setLevel(logging.CRITICAL)

logger = logging.getLogger("InstagramBot")
