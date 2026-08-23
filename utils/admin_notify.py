import hashlib
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions
from config import ADMIN_ID


def _user_label(user):
    username = f"@{user.username}" if user.username else "без username"
    return f"{user.first_name or '-'} ({username}, id={user.id})"


async def notify_admin_user_message(context, update, text: str):
    user = update.effective_user
    if user is None or user.id == ADMIN_ID:
        return

    message_text = text.strip()
    if not message_text:
        return

    alerts = context.application.bot_data.setdefault("admin_user_alerts", {})
    alert_key = str(user.id)
    now = time.monotonic()
    if now - alerts.get(alert_key, 0) < 600:
        return
    alerts[alert_key] = now

    # Avoid sending the same user message twice during rapid duplicate updates.
    fingerprint = hashlib.sha256(
        f"{user.id}:{message_text}".encode("utf-8", "replace")
    ).hexdigest()
    recent = context.application.bot_data.setdefault("admin_user_messages", {})
    now = time.monotonic()
    if now - recent.get(fingerprint, 0) < 30:
        return
    recent[fingerprint] = now

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            "✉️ Сообщение от пользователя\n\n"
            f"👤 {_user_label(user)}\n"
            f"💬 {message_text[:3000]}"
        ),
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("✉️ Ответить", callback_data=f"admin_reply:{user.id}")]]
        ),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


async def notify_admin_error(context, update, error):
    """Send a deduplicated error alert to the administrator."""
    error_text = str(error or "Unknown error")
    fingerprint = hashlib.sha256(error_text.encode("utf-8", "replace")).hexdigest()
    now = time.monotonic()
    sent_errors = context.application.bot_data.setdefault("admin_error_alerts", {})
    last_sent = sent_errors.get(fingerprint, 0)
    if now - last_sent < 300:
        return
    sent_errors[fingerprint] = now

    user = getattr(update, "effective_user", None)
    user_line = _user_label(user) if user else "пользователь неизвестен"
    reply_markup = None
    if user:
        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("✉️ Ответить", callback_data=f"admin_reply:{user.id}")]]
        )

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            "🚨 Ошибка бота\n\n"
            f"👤 {user_line}\n"
            f"⚠️ {error_text[:3000]}"
        ),
        reply_markup=reply_markup,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
