import json

from telegram import Update
from telegram.ext import ContextTypes

from config import MAX_URL_LENGTH
from handlers.download import _handle_message_locked
from services import extract_service_link
from utils.message_utils import require_effective_user, require_message_target
from utils.user_locks import get_user_lock


async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forward a Mini App URL to the bot's existing download workflow."""
    message = require_message_target(update)
    web_app_data = message.web_app_data
    if web_app_data is None:
        return

    try:
        payload = json.loads(web_app_data.data)
    except (TypeError, json.JSONDecodeError):
        await message.reply_text("⚠️ Не удалось прочитать ссылку. Откройте приложение и попробуйте ещё раз.")
        return

    url = payload.get("url") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or payload.get("action") != "download"
        or not isinstance(url, str)
        or not url.strip()
        or len(url) > MAX_URL_LENGTH
    ):
        await message.reply_text("⚠️ Ссылка не распознана или слишком длинная. Отправьте её боту в чат.")
        return

    url = url.strip()
    service, extracted_url = extract_service_link(url)
    if service is None or extracted_url != url:
        await message.reply_text("⚠️ Эта ссылка пока не поддерживается. Попробуйте отправить её боту в чат.")
        return

    user = require_effective_user(update)
    lock = await get_user_lock(context, user.id)
    async with lock:
        await _handle_message_locked(update, context, message, url)
