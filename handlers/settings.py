from telegram import Update
from telegram.ext import ContextTypes

from database.database import clear_history, get_user_settings, update_user_settings
from keyboards.settings import (
    confirm_clear_keyboard,
    format_keyboard,
    history_keyboard,
    language_keyboard,
    settings_keyboard,
)
from keyboards.main_menu import main_menu
from utils.i18n import translate


def settings_text(settings):
    language = settings["language"]
    return translate(
        language,
        "settings_title",
        format=translate(language, f"format_{settings['send_format']}"),
        history=translate(
            language,
            "history_on" if settings["history_enabled"] else "history_off",
        ),
        lang=translate(language, f"language_{language}"),
    )


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings = get_user_settings(update.effective_user.id)
    await update.message.reply_text(
        settings_text(settings),
        reply_markup=settings_keyboard(settings),
    )


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    settings = get_user_settings(user_id)
    language = settings["language"]
    action = query.data

    if action == "settings:home":
        await query.edit_message_text(
            settings_text(settings),
            reply_markup=settings_keyboard(settings),
        )
    elif action == "settings:format":
        await query.edit_message_text(
            translate(language, "choose_format"),
            reply_markup=format_keyboard(language),
        )
    elif action == "settings:history":
        await query.edit_message_text(
            translate(language, "choose_history"),
            reply_markup=history_keyboard(language),
        )
    elif action == "settings:language":
        await query.edit_message_text(
            translate(language, "choose_language"),
            reply_markup=language_keyboard(language),
        )
    elif action == "settings:history:clear":
        await query.edit_message_text(
            translate(language, "confirm_clear"),
            reply_markup=confirm_clear_keyboard(language),
        )
    elif action == "settings:history:clear:yes":
        clear_history(user_id)
        settings = get_user_settings(user_id)
        await query.edit_message_text(
            translate(settings["language"], "history_cleared") + "\n\n" + settings_text(settings),
            reply_markup=settings_keyboard(settings),
        )
    elif action.startswith("settings:format:"):
        update_user_settings(user_id, send_format=action.rsplit(":", 1)[1])
        settings = get_user_settings(user_id)
        await query.edit_message_text(
            translate(settings["language"], "setting_saved") + "\n\n" + settings_text(settings),
            reply_markup=settings_keyboard(settings),
        )
    elif action.startswith("settings:history:"):
        history_enabled = action.rsplit(":", 1)[1] == "on"
        update_user_settings(user_id, history_enabled=int(history_enabled))
        settings = get_user_settings(user_id)
        await query.edit_message_text(
            translate(settings["language"], "setting_saved") + "\n\n" + settings_text(settings),
            reply_markup=settings_keyboard(settings),
        )
    elif action.startswith("settings:language:"):
        update_user_settings(user_id, language=action.rsplit(":", 1)[1])
        settings = get_user_settings(user_id)
        await query.edit_message_text(
            translate(settings["language"], "setting_saved") + "\n\n" + settings_text(settings),
            reply_markup=settings_keyboard(settings),
        )
        await query.message.reply_text(
            translate(settings["language"], "main_menu"),
            reply_markup=main_menu(settings["language"]),
        )
