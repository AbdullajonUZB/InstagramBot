from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from database.database import get_history, get_user_settings
from handlers.settings import show_settings
from keyboards.main_menu import main_menu
from utils.i18n import translate
from handlers.profile import profile_command
from handlers.history import history_keyboard
from services import SERVICES
from utils.message_utils import require_effective_user, require_message_target
from utils.telegram_retry import reply_text_with_retry
from utils.admin_roles import is_admin
from utils.chat_cleanup import clear_ui_messages, delete_button_message, remember_ui_message


def compact_history_date(created_at):
    """Format a history timestamp for a short mobile-friendly list."""
    value = str(created_at or "")
    try:
        return datetime.fromisoformat(value).strftime("%d.%m %H:%M")
    except ValueError:
        return value[:16] if value else ""


def get_action(text: str) -> str | None:
    for language in ("ru", "uz", "en"):
        for action in ("download", "history", "settings", "help", "back"):
            if text == translate(language, action):
                return action
    return None


def help_keyboard(language: str, show_news: bool = True):
    label_key = "help_news_button" if show_news else "help_back_button"
    callback = "help:news" if show_news else "help:home"
    return InlineKeyboardMarkup([[InlineKeyboardButton(translate(language, label_key), callback_data=callback)]])

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = require_message_target(update)
    if not isinstance(message.text, str):
        return
    text = message.text
    user_id = require_effective_user(update).id
    settings = get_user_settings(user_id)
    language = settings["language"]
    action = get_action(text)
    is_service_button = text in [service["button"] for service in SERVICES.values()]
    is_menu_button = action is not None or is_service_button or text in {"🛠 Админ-панель", "👤 Профиль"}
    if is_menu_button:
        await clear_ui_messages(context, message.chat_id)

    if action == "download":
        context.user_data.pop("selected_service", None)
        prompt = await reply_text_with_retry(
            message,
            "🔗 Отправьте ссылку на видео или публикацию.",
            reply_markup=main_menu(language, include_admin=is_admin(user_id)),
        )
        context.user_data["download_prompt_message_id"] = prompt.message_id
        remember_ui_message(context, prompt)

    elif is_service_button:

        print("SERVICE BUTTON PRESSED:", text)

        for key, service in SERVICES.items():
            if text == service["button"]:
                context.user_data["selected_service"] = key

                print("selected_service =", key)

                reply = await reply_text_with_retry(
                    message,
                    translate(
                        language,
                        "send_service_link",
                        service=service["button"][2:],
                    ),
                )
                remember_ui_message(context, reply)

                break

    elif action == "back":
        context.user_data.pop("selected_service", None)
        reply = await reply_text_with_retry(
            message,
            translate(language, "main_menu"),
            reply_markup=main_menu(language),
        )
        remember_ui_message(context, reply)

    elif action == "history":
        history = get_history(user_id)

        if not history:
            reply = await reply_text_with_retry(message, translate(language, "history_empty"))
            remember_ui_message(context, reply)
            await delete_button_message(message)
            return

        history_text = translate(language, "history_title")
        for index, item in enumerate(history, start=1):
            file_type, _url, created_at = item
            history_text += f"{index}. {file_type} · {compact_history_date(created_at)}\n"

        reply = await reply_text_with_retry(message, history_text, reply_markup=history_keyboard(history))
        remember_ui_message(context, reply)
    elif action == "settings":
        await show_settings(update, context)

    elif action == "help":
        reply = await reply_text_with_retry(
            message,
            translate(language, "help_text"),
            reply_markup=help_keyboard(language),
        )
        remember_ui_message(context, reply)
    elif text == "🛠 Админ-панель" and is_admin(user_id):
        await from_admin_panel(update, context)
    elif text == "👤 Профиль":
        await profile_command(update, context)

    if is_menu_button:
        await delete_button_message(message)


async def from_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from handlers.admin import admin_panel

    await admin_panel(update, context)


async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None or not query.data:
        return
    await query.answer()
    language = get_user_settings(require_effective_user(update).id)["language"]
    show_news = query.data == "help:news"
    key = "news_text" if show_news else "help_text"
    await query.edit_message_text(
        translate(language, key),
        reply_markup=help_keyboard(language, show_news=not show_news),
    )
