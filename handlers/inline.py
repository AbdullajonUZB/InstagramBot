"""Inline-mode link previews for supported media services."""

import hashlib

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from telegram.ext import ContextTypes

from services import SERVICES, extract_service_link


INLINE_QUERY_MAX_LENGTH = 2000


def build_inline_result(service_key: str, url: str, bot_username: str):
    service = SERVICES[service_key]
    service_name = service["button"].split(" ", 1)[-1]
    result_id = hashlib.sha256(f"{service_key}:{url}".encode("utf-8")).hexdigest()[:32]
    return InlineQueryResultArticle(
        id=result_id,
        title=f"📥 Ссылка из {service_name}",
        description="Отправить ссылку в чат; для скачивания откройте бота",
        input_message_content=InputTextMessageContent(
            message_text=(
                f"📥 Ссылка на публикацию ({service_name}):\n{url}\n\n"
                "Чтобы скачать, откройте бота и отправьте ему эту ссылку."
            )
        ),
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("📥 Открыть бота", url=f"https://t.me/{bot_username}")]]
        ),
    )


async def handle_inline_query(update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query
    if query is None:
        return

    text = (query.query or "").strip()
    results = []
    if len(text) <= INLINE_QUERY_MAX_LENGTH:
        service_key, url = extract_service_link(text)
        if service_key and url:
            bot = await context.bot.get_me()
            if bot.username:
                results = [build_inline_result(service_key, url, bot.username)]

    await query.answer(results, cache_time=5, is_personal=True)
