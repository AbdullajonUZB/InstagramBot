from multiprocessing import context
from pydoc import text
from turtle import update
from telegram import Update
from telegram.ext import ContextTypes
from database.database import get_history, get_user_settings
from handlers.settings import show_settings
from keyboards.main_menu import main_menu, service_menu
from utils.i18n import translate
from handlers.profile import profile_command
from services import SERVICES
from utils.message_utils import get_message_target


def get_action(text):
    for language in ("ru", "uz", "en"):
        for action in ("download", "history", "settings", "help", "back"):
            if text == translate(language, action):
                return action
    return None

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = get_message_target(update)
    text = getattr(message, "text", None)
    user_id = update.effective_user.id
    settings = get_user_settings(user_id)
    language = settings["language"]
    action = get_action(text)

    if action == "download":
        context.user_data.pop("selected_service", None)
        await message.reply_text(
            translate(language, "choose_service"),
            reply_markup=service_menu(language),
        )

    elif text in [service["button"] for service in SERVICES.values()]:

        print("SERVICE BUTTON PRESSED:", text)

        for key, service in SERVICES.items():
            if text == service["button"]:
                context.user_data["selected_service"] = key

                print("selected_service =", key)

                await message.reply_text(
                    translate(
                        language,
                        "send_service_link",
                        service=service["button"][2:],
                    ),
                )

                break

    elif action == "back":
        context.user_data.pop("selected_service", None)
        await message.reply_text(
            translate(language, "main_menu"),
            reply_markup=main_menu(language),
        )

    elif action == "history":
        history = get_history(user_id)

        if not history:
            await message.reply_text(translate(language, "history_empty"))
            return

        message = translate(language, "history_title")
        for index, item in enumerate(history, start=1):
            file_type, url, created_at = item
            message += f"{index}. {file_type}\n📅 {created_at}\n🔗 {url}\n\n"

        await message.reply_text(message)

    elif action == "settings":
        await show_settings(update, context)

    elif action == "help":
        await message.reply_text(translate(language, "help_text"))
    elif text == "👤 Профиль":
        await profile_command(update, context)