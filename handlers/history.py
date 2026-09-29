from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import downloaders.instagram
import downloaders.pinterest
import downloaders.tiktok
import downloaders.youtube
from database.database import get_history_item
from services import SERVICES, extract_service_link
from utils.followup_media import clear_followup_media
from utils.message_utils import require_effective_user, require_message_target
from utils.user_locks import get_user_lock
from utils.chat_cleanup import delete_message_safely


def history_keyboard(history):
    rows = []
    current_row = []
    for index, (file_type, _url, _created_at) in enumerate(history, start=1):
        label = "🎵" if "аудио" in str(file_type).lower() else "📥"
        current_row.append(
            InlineKeyboardButton(
                f"{label} №{index}",
                callback_data=f"history:download:{index}",
            )
        )
        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)
    return InlineKeyboardMarkup(rows) if rows else None


async def history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None or not query.data:
        return
    await query.answer()
    parts = query.data.split(":")
    if len(parts) != 3 or parts[1] != "download":
        return

    user = require_effective_user(update)
    try:
        item_number = int(parts[2])
    except ValueError:
        return
    item = get_history_item(user.id, item_number)
    message = require_message_target(update)
    if item is None:
        await message.reply_text("⚠️ Запись истории больше недоступна.")
        return

    file_type, url, _created_at = item
    service_key, detected_url = extract_service_link(url)
    if service_key is None or detected_url is None:
        await message.reply_text("⚠️ Не удалось определить сервис этой записи.")
        return

    lock = await get_user_lock(context, user.id)
    async with lock:
        clear_followup_media(context)
        status_message = await message.reply_text("⏳ Повторное скачивание началось...")
        try:
            if service_key == "youtube":
                success = await downloaders.youtube.download_youtube(
                    update,
                    context,
                    detected_url,
                    choice="audio" if "аудио" in str(file_type).lower() else "video",
                )
            else:
                downloader = SERVICES[service_key]["downloader"]
                success = await downloader(update, context, detected_url)
        finally:
            try:
                await status_message.delete()
            except Exception:
                pass

        if success is True:
            from handlers.download import download_actions_keyboard

            await message.reply_text(
                "✅ Готово. Что сделать дальше?",
                reply_markup=download_actions_keyboard(bool(context.user_data.get("followup_media_path"))),
            )
            await delete_message_safely(query.message)
