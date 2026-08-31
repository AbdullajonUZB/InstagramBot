from telegram import Update
from telegram.ext import ContextTypes
from database.database import get_history, get_user_settings
from handlers.settings import show_settings
from keyboards.main_menu import main_menu
from utils.i18n import translate
from handlers.profile import profile_command
from services import SERVICES
from utils.message_utils import require_effective_user, require_message_target
from utils.telegram_retry import reply_text_with_retry
from utils.admin_roles import is_admin


def get_action(text: str) -> str | None:
    for language in ("ru", "uz", "en"):
        for action in ("download", "history", "settings", "help", "back"):
            if text == translate(language, action):
                return action
    return None

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = require_message_target(update)
    if not isinstance(message.text, str):
        return
    text = message.text
    user_id = require_effective_user(update).id
    settings = get_user_settings(user_id)
    language = settings["language"]
    action = get_action(text)

    if action == "download":
        context.user_data.pop("selected_service", None)
        prompt = await reply_text_with_retry(
            message,
            "🔗 Отправьте ссылку на видео или публикацию.",
            reply_markup=main_menu(language, include_admin=is_admin(user_id)),
        )
        context.user_data["download_prompt_message_id"] = prompt.message_id

    elif text in [service["button"] for service in SERVICES.values()]:

        print("SERVICE BUTTON PRESSED:", text)

        for key, service in SERVICES.items():
            if text == service["button"]:
                context.user_data["selected_service"] = key

                print("selected_service =", key)

                await reply_text_with_retry(
                    message,
                    translate(
                        language,
                        "send_service_link",
                        service=service["button"][2:],
                    ),
                )

                break

    elif action == "back":
        context.user_data.pop("selected_service", None)
        await reply_text_with_retry(
            message,
            translate(language, "main_menu"),
            reply_markup=main_menu(language),
        )

    elif action == "history":
        history = get_history(user_id)

        if not history:
            await reply_text_with_retry(message, translate(language, "history_empty"))
            return

        history_text = translate(language, "history_title")
        for index, item in enumerate(history, start=1):
            file_type, url, created_at = item
            history_text += f"{index}. {file_type}\n📅 {created_at}\n🔗 {url}\n\n"

        await reply_text_with_retry(message, history_text)
    elif action == "settings":
        await show_settings(update, context)

    elif action == "help":
        await reply_text_with_retry(message, translate(language, "help_text"))
    elif text == "🛠 Админ-панель" and is_admin(user_id):
        await from_admin_panel(update, context)
    elif text == "👤 Профиль":
        await profile_command(update, context)


async def from_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from handlers.admin import admin_panel

    await admin_panel(update, context)
