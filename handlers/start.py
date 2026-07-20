from telegram import Update
from telegram.ext import ContextTypes

from keyboards.main_menu import main_menu
from database.database import get_user_settings
from utils.i18n import translate


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    language = get_user_settings(update.effective_user.id)["language"]

    await update.message.reply_text(
        translate(language, "welcome"),
        reply_markup=main_menu(language),
    )
