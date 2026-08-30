import time
from collections import defaultdict, deque

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from config import ADMIN_IDS, MAX_MESSAGE_LENGTH, MAX_URL_LENGTH
from database.database import is_user_banned


COOLDOWN_SECONDS = 2
FLOOD_WINDOW_SECONDS = 60
FLOOD_LIMIT = 10
AUTO_BAN_SECONDS = 600


async def security_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user is None or user.id in ADMIN_IDS:
        return

    message = update.effective_message
    text = getattr(message, "text", None) or getattr(message, "caption", None)
    if isinstance(text, str) and len(text) > MAX_MESSAGE_LENGTH:
        await _stop_update(update, "⚠️ Сообщение слишком длинное.")
        raise ApplicationHandlerStop
    if isinstance(text, str) and "http" in text.lower() and len(text) > MAX_URL_LENGTH:
        await _stop_update(update, "⚠️ Ссылка слишком длинная или некорректная.")
        raise ApplicationHandlerStop

    if is_user_banned(user.id):
        await _stop_update(update, "🚫 Доступ к боту ограничен.")
        raise ApplicationHandlerStop

    now = time.monotonic()
    data = context.application.bot_data
    last_updates = data.setdefault("security_last_update", {})
    flood_events = data.setdefault("security_flood_events", defaultdict(deque))
    muted_until = data.setdefault("security_muted_until", {})

    if muted_until.get(user.id, 0) > now:
        await _stop_update(update, "⏳ Слишком много сообщений. Попробуйте через несколько минут.")
        raise ApplicationHandlerStop

    if now - last_updates.get(user.id, 0) < COOLDOWN_SECONDS:
        events = flood_events[user.id]
        events.append(now)
        while events and now - events[0] > FLOOD_WINDOW_SECONDS:
            events.popleft()
        if len(events) >= FLOOD_LIMIT:
            muted_until[user.id] = now + AUTO_BAN_SECONDS
            await _stop_update(update, "🚫 Вы временно заблокированы за слишком частые сообщения.")
            raise ApplicationHandlerStop
        await _stop_update(update, "⏳ Не отправляйте сообщения так часто.")
        raise ApplicationHandlerStop

    last_updates[user.id] = now


async def _stop_update(update: Update, text: str):
    message = update.effective_message
    if message is not None:
        try:
            await message.reply_text(text)
        except Exception:
            pass
