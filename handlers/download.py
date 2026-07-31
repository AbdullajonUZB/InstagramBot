import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import downloaders.instagram
import downloaders.pinterest
import downloaders.tiktok
import downloaders.youtube
from keyboards.main_menu import service_menu
from database.database import get_user_settings
from utils.i18n import translate
from services import SERVICES
from utils.message_utils import get_message_target

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = get_message_target(update)
    if not message or not getattr(message, "text", None):
        return

    text = message.text.strip()
    language = get_user_settings(update.effective_user.id)["language"]

    selected_service = context.user_data.get("selected_service")
    if not selected_service:
        message = get_message_target(update)
        await message.reply_text(
            translate(language, "choose_first"),
            reply_markup=service_menu(language),
        )
        return

    service = SERVICES[selected_service]
    service_name = service["button"][2:]
    pattern = service["pattern"]
    downloader = service["downloader"]

    match = re.search(pattern, text)
    if not match:
        message = get_message_target(update)
        await message.reply_text(
            translate(language, "wrong_service_link", service=service_name)
        )
        return

    url = match.group(1)

    if selected_service == "youtube":
        context.user_data["pending_youtube_url"] = url
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🎥 Видео", callback_data="youtube_select:video"),
                    InlineKeyboardButton("🎵 Музыка (MP3)", callback_data="youtube_select:audio"),
                ]
            ]
        )
        message = get_message_target(update)
        await message.reply_text(
            "🎬 Что вы хотите скачать?",
            reply_markup=keyboard,
        )
        return

    message = get_message_target(update)
    status_message = await message.reply_text(
        translate(language, "downloading")
    )

    success = await downloader(
        update,
        context,
        url,
    )

    try:
        await status_message.delete()
    except Exception:
        pass

    if not success:
        await message.reply_text(
            translate(language, "download_failed")
        )


async def handle_youtube_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not query.data:
        return

    choice = query.data.split(":", 1)[1]
    pending_url = context.user_data.get("pending_youtube_url")
    if not pending_url:
        await query.message.reply_text("⚠️ Ссылка для YouTube была потеряна. Попробуйте отправить её ещё раз.")
        return

    context.user_data.pop("pending_youtube_url", None)
    status_message = await query.message.reply_text("⏳ Скачивание началось...")

    try:
        success = await downloaders.youtube.download_youtube(
            update,
            context,
            pending_url,
            choice=choice,
        )
    finally:
        try:
            await status_message.delete()
        except Exception:
            pass

    if success is False:
        await query.message.reply_text("❌ Не удалось скачать файл.")
    elif success is None:
        await query.message.reply_text("⚠️ Не удалось отправить файл в Telegram. Попробуйте ещё раз.")
