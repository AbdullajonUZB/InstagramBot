from turtle import update

from telegram import Update
from telegram.ext import ContextTypes

from database.database import get_history, get_user_settings
from handlers.settings import show_settings
from keyboards.main_menu import main_menu, service_menu
from utils.i18n import translate
from handlers.profile import profile_command

SERVICE_BUTTONS = {
    "📷 Instagram": "instagram",
    "▶️ YouTube": "youtube",
    "🎵 TikTok": "tiktok",
    "📌 Pinterest": "pinterest",
}


def get_action(text):
    for language in ("ru", "uz", "en"):
        for action in ("download", "history", "settings", "help", "back"):
            if text == translate(language, action):
                return action
    return None


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    settings = get_user_settings(user_id)
    language = settings["language"]
    action = get_action(text)

    if action == "download":
        context.user_data.pop("selected_service", None)
        await update.message.reply_text(
            translate(language, "choose_service"),
            reply_markup=service_menu(language),
        )

    elif text in SERVICE_BUTTONS:
        context.user_data["selected_service"] = SERVICE_BUTTONS[text]
        await update.message.reply_text(
            translate(language, "send_service_link", service=text[2:]),
        )

    elif action == "back":
        context.user_data.pop("selected_service", None)
        await update.message.reply_text(
            translate(language, "main_menu"),
            reply_markup=main_menu(language),
        )

    elif action == "history":
        history = get_history(user_id)

        if not history:
            await update.message.reply_text(translate(language, "history_empty"))
            return

        message = translate(language, "history_title")
        for index, item in enumerate(history, start=1):
            file_type, url, created_at = item
            message += f"{index}. {file_type}\n📅 {created_at}\n🔗 {url}\n\n"

        await update.message.reply_text(message)

    elif action == "settings":
        await show_settings(update, context)

    elif action == "help":
        await update.message.reply_text(translate(language, "help_text"))
    elif text == "👤 Профиль":
        await profile_command(update, context)