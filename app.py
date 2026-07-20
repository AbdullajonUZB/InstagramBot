import logging

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
from config import BOT_TOKEN
from handlers.start import start
from handlers.download import handle_message
from handlers.menu import menu
from handlers.admin import db
from handlers.settings import settings_callback
from database.database import create_database
from handlers.profile import profile_command

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


def main():

    create_database()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("db", db))
    app.add_handler(CallbackQueryHandler(settings_callback, pattern=r"^settings:"))
    app.add_handler(
    MessageHandler(
        filters.Regex(
            r"^(📥 Скачать|📥 Yuklab olish|📥 Download|"
            r"📜 История|📜 Tarix|📜 History|"
            r"⚙ Настройки|⚙ Sozlamalar|⚙ Settings|"
            r"ℹ️ Помощь|ℹ️ Yordam|ℹ️ Help|"
            r"📷 Instagram|▶️ YouTube|🎵 TikTok|📌 Pinterest|"
            r"⬅️ Назад|⬅️ Orqaga|⬅️ Back)$"
        ),
        menu,
    )
)
    app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message,
        )
    )

    logger.info("=" * 50)
    logger.info("Instagram Downloader")
    logger.info("Администратор подключён")
    logger.info("=" * 5)

    app.run_polling()

if __name__ == "__main__":
    main()
