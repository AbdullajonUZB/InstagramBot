from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from config import BOT_TOKEN
from database.database import create_database

from handlers.start import start
from handlers.download import handle_message
from handlers.menu import menu
from handlers.admin import db
from handlers.settings import settings_callback
from handlers.profile import profile_command
from handlers.error import error_handler

from utils.logger import logger


logger.info("Initializing Instagram Downloader...")


def main():
    create_database()

    app = Application.builder().token(BOT_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("db", db))

    # Callback
    app.add_handler(
        CallbackQueryHandler(
            settings_callback,
            pattern=r"^settings:"
        )
    )
    app.add_handler(
        MessageHandler(
            filters.Regex(
                r"^(👤 Профиль|"
                r"📥 Скачать|📥 Yuklab olish|📥 Download|"
                r"📜 История|📜 Tarix|📜 History|"
                r"⚙ Настройки|⚙ Sozlamalar|⚙ Settings|"
                r"ℹ️ Помощь|ℹ️ Yordam|ℹ️ Help|"
                r"📷 Instagram|▶️ YouTube|🎵 TikTok|📌 Pinterest|"
                r"⬅️ Назад|⬅️ Orqaga|⬅️ Back)$"
            ),
            menu,
        ),
        group=0,
    )
    app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND
            & ~filters.Regex(
                r"^(👤 Профиль|"
                r"📥 Скачать|📥 Yuklab olish|📥 Download|"
                r"📜 История|📜 Tarix|📜 History|"
                r"⚙ Настройки|⚙ Sozlamalar|⚙ Settings|"
                r"ℹ️ Помощь|ℹ️ Yordam|ℹ️ Help|"
                r"📷 Instagram|▶️ YouTube|🎵 TikTok|📌 Pinterest|"
                r"⬅️ Назад|⬅️ Orqaga|⬅️ Back)$"
            ),
            handle_message,
        ),
        group=1,
    )
    # Глобальный обработчик ошибок
    app.add_error_handler(error_handler)
    logger.info("=" * 50)
    logger.info("Instagram Downloader started")
    logger.info("=" * 50)

    app.run_polling()
if __name__ == "__main__":
    main()