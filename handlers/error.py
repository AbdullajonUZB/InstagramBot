from telegram import Update
from telegram.ext import ContextTypes
from utils.logger import logger


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Exception while handling an update:", exc_info=context.error)

    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Произошла ошибка. Попробуйте ещё раз."
            )
        except Exception:
            pass