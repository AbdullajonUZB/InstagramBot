from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
from config import (
    BOT_TOKEN,
    TELEGRAM_CONNECT_TIMEOUT,
    TELEGRAM_GET_UPDATES_READ_TIMEOUT,
    TELEGRAM_POOL_TIMEOUT,
    TELEGRAM_READ_TIMEOUT,
    TELEGRAM_WRITE_TIMEOUT,
)
from database.database import create_database
from handlers.start import main_menu_callback, start
from handlers.download import (
    handle_download_ui_callback,
    handle_message,
    handle_youtube_choice,
)
from handlers.menu import menu
from handlers.admin import (
    admin_status,
    cancel_admin_reply,
    db,
    handle_admin_reply_callback,
    handle_admin_reply_message,
    handle_bonus_request,
    handle_premium_stub,
    handle_admin_bonus_action,
)
from handlers.settings import settings_callback
from handlers.profile import profile_command
from handlers.error import error_handler
from handlers.video_tools import VideoToolsHandler
from handlers.feedback import feedback_callback
from keyboards.navigation import delete_message_callback
from utils.logger import logger

logger.info("Initializing Instagram Downloader...")

video_tools_handler = VideoToolsHandler()


def main():
    create_database()

    # Handlers await long-running downloads; process different users' updates
    # concurrently instead of waiting for one update to finish first.
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(TELEGRAM_CONNECT_TIMEOUT)
        .read_timeout(TELEGRAM_READ_TIMEOUT)
        .write_timeout(TELEGRAM_WRITE_TIMEOUT)
        .pool_timeout(TELEGRAM_POOL_TIMEOUT)
        .get_updates_connect_timeout(TELEGRAM_CONNECT_TIMEOUT)
        .get_updates_read_timeout(TELEGRAM_GET_UPDATES_READ_TIMEOUT)
        .get_updates_write_timeout(TELEGRAM_WRITE_TIMEOUT)
        .get_updates_pool_timeout(TELEGRAM_POOL_TIMEOUT)
        .concurrent_updates(True)
        .build()
    )

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("db", db))
    app.add_handler(CommandHandler("admin_status", admin_status))
    app.add_handler(CommandHandler("cancel_reply", cancel_admin_reply))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_admin_reply_message,
        ),
        group=-1,
    )

    # Callback
    app.add_handler(
        CallbackQueryHandler(
            settings_callback,
            pattern=r"^settings:"
        )
    )
    app.add_handler(
        CallbackQueryHandler(handle_bonus_request, pattern=r"^bonus_request$")
    )
    app.add_handler(
        CallbackQueryHandler(handle_premium_stub, pattern=r"^premium_stub$")
    )
    app.add_handler(
        CallbackQueryHandler(handle_admin_bonus_action, pattern=r"^admin_bonus:")
    )
    app.add_handler(
        CallbackQueryHandler(handle_admin_reply_callback, pattern=r"^admin_reply:")
    )
    app.add_handler(
        CallbackQueryHandler(handle_youtube_choice, pattern=r"^youtube_select:")
    )
    app.add_handler(
        CallbackQueryHandler(handle_download_ui_callback, pattern=r"^download_ui:")
    )
    app.add_handler(
        CallbackQueryHandler(main_menu_callback, pattern=r"^main_menu$")
    )
    app.add_handler(
        CallbackQueryHandler(delete_message_callback, pattern=r"^delete_message$")
    )
    app.add_handler(
        CallbackQueryHandler(feedback_callback, pattern=r"^feedback:")
    )
    app.add_handler(
        CallbackQueryHandler(video_tools_handler.handle_callback, pattern=r"^video_tools:")
    )
    app.add_handler(
        MessageHandler(
            filters.Regex(r"^🎵 Видео → MP3$"),
            video_tools_handler.handle_main_menu,
        ),
        group=0,
    )
    app.add_handler(
        MessageHandler(
            filters.VIDEO,
            video_tools_handler.handle_video_message,
        ),
        group=0,
    )
    app.add_handler(
        MessageHandler(
            filters.Regex(
                r"^(👤 Профиль|"
                r"📥 Скачать|📥 Yuklab olish|📥 Download|"
                r"📜 История|📜 Tarix|📜 History|"
                r"⚙ Настройки|⚙ Sozlamalar|⚙ Settings|"
                r"ℹ️ Помощь|ℹ️ Yordam|ℹ️ Help|"
                r"📷 Instagram|▶️ YouTube|🎵 TikTok|📌 Pinterest|📘 Facebook|"
                r"🎵 Видео → MP3|"
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
                r"📷 Instagram|▶️ YouTube|🎵 TikTok|📌 Pinterest|📘 Facebook|"
                r"🎵 Видео → MP3|"
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
