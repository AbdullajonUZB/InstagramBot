from telegram import Update
from telegram.error import NetworkError, TimedOut
from telegram.ext import ContextTypes
from utils.logger import logger
from utils.admin_notify import notify_admin_error


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Exception while handling an update:", exc_info=context.error)

    # Network errors are transient and are already retried by the polling
    # loop. Do not create an additional admin alert for every reconnect.
    if not isinstance(context.error, (NetworkError, TimedOut)):
        try:
            await notify_admin_error(context, update, context.error)
        except Exception:
            logger.exception("Failed to notify administrator about an error")

    if isinstance(update, Update) and update.effective_message is not None:
        try:
            if isinstance(context.error, (NetworkError, TimedOut)):
                text = "🔄 Сервер или бот временно обновляется. Попробуйте ещё раз через минуту."
            else:
                text = "❌ Произошла ошибка. Попробуйте ещё раз."
            await update.effective_message.reply_text(text)
        except Exception:
            pass
