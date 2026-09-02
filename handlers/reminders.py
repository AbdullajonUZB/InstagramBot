from telegram import Update
from telegram.ext import ContextTypes

from database.database import get_user_settings, set_reminders_enabled
from keyboards.main_menu import main_menu
from utils.message_utils import require_effective_user


async def reminder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None:
        return
    user_id = require_effective_user(update).id
    await query.answer()
    if query.data == "reminder:disable":
        set_reminders_enabled(user_id, False)
        try:
            await query.edit_message_text("🔕 Хорошо, больше не буду присылать напоминания.")
        except Exception:
            pass
    elif query.data == "reminder:download" and query.message is not None:
        language = get_user_settings(user_id)["language"]
        await query.message.reply_text("🔗 Отправьте ссылку на видео или публикацию.", reply_markup=main_menu(language))
