from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import sqlite3

from config import ADMIN_ID
from database.database import (
    add_security_log,
    approve_bonus_request,
    create_bonus_download_request,
    decline_bonus_request,
    get_bonus_request,
    get_user_profile,
    get_user_settings,
    get_user_total_downloads,
    has_active_bonus_request,
    FREE_DAILY_LIMIT,
)
from utils.i18n import translate


async def db(update: Update, context: ContextTypes.DEFAULT_TYPE):

    language = get_user_settings(update.effective_user.id)["language"]

    if update.effective_user.id != ADMIN_ID:

        add_security_log(
            update.effective_user.id,
            update.effective_user.username,
            update.effective_user.first_name,
            "ACCESS_DENIED",
            "/db"
        )

        await update.message.reply_text(
            translate(language, "access_denied")
        )

        return

    conn = sqlite3.connect("database/history.db")

    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        username,
        media_type,
        status,
        created_at
    FROM downloads
    ORDER BY id DESC
    LIMIT 10
    """)

    rows = cursor.fetchall()

    conn.close()

    if not rows:

        await update.message.reply_text(
            translate(language, "admin_history_empty")
        )

        return

    text = translate(language, "admin_history_title")

    for row in rows:

        username = row[0] or "Без username"

        text += (
            f"👤 {username}\n"
            f"📂 {row[1]}\n"
            f"📌 {row[2]}\n"
            f"🕒 {row[3]}\n\n"
        )

    await update.message.reply_text(text)


async def handle_premium_stub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⭐ Premium будет добавлен позже.")
    await query.message.reply_text("⭐ Premium будет добавлен позже.")


async def handle_bonus_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    await query.answer()

    if has_active_bonus_request(user.id):
        await query.message.reply_text(
            "⏳ Ваш запрос уже отправлен.\n"
            "Пожалуйста, дождитесь решения администратора."
        )
        return

    request_id = create_bonus_download_request(
        user.id,
        user.username,
        user.first_name,
    )

    if not request_id:
        await query.message.reply_text(
            "⏳ Ваш запрос уже отправлен.\n"
            "Пожалуйста, дождитесь решения администратора."
        )
        return

    profile = get_user_profile(user.id) or (None, None, 0, None, 0, None, 0)
    first_name, username, is_premium, premium_until, downloads_today, registered_at, bonus_downloads_total = profile
    total_downloads = get_user_total_downloads(user.id)

    admin_text = (
        "📢 Новый запрос на дополнительные скачивания\n\n"
        f"👤 Имя пользователя: {first_name or '-'}\n"
        f"🔗 Username: @{username if username else '-'}\n"
        f"🆔 Telegram ID: {user.id}\n\n"
        f"📊 Сегодня использовано: {downloads_today}/{FREE_DAILY_LIMIT}\n"
        f"📈 Всего скачиваний: {total_downloads}\n"
        f"📅 Дата регистрации: {registered_at or '-'}\n"
        f"🎁 Сколько раз ранее получал дополнительные скачивания: {bonus_downloads_total}\n\n"
        f"🕒 Дата и время запроса: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ +5", callback_data=f"admin_bonus:approve:5:{request_id}"),
                InlineKeyboardButton("➕ +10", callback_data=f"admin_bonus:approve:10:{request_id}"),
                InlineKeyboardButton("➕ +20", callback_data=f"admin_bonus:approve:20:{request_id}"),
            ],
            [InlineKeyboardButton("❌ Отказать", callback_data=f"admin_bonus:decline:0:{request_id}")],
        ]
    )

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=admin_text,
        reply_markup=keyboard,
    )
    await query.message.reply_text(
        "✅ Ваш запрос отправлен администратору.\n"
        "Ожидайте решения."
    )


async def handle_admin_bonus_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if update.effective_user.id != ADMIN_ID:
        await query.answer("Доступ запрещён.", show_alert=True)
        return

    await query.answer()

    parts = query.data.split(":")
    if len(parts) != 4:
        return

    action, decision, amount, request_id = parts[1], parts[1], parts[2], parts[3]
    request_id = int(request_id)
    amount = int(amount)

    request = get_bonus_request(request_id)
    if not request:
        await query.edit_message_text("❌ Запрос уже неактивен.", reply_markup=None)
        return

    if decision == "approve":
        approved = approve_bonus_request(request_id, amount, ADMIN_ID)
        if approved:
            user_id = request[1]
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "🎉 Администратор одобрил ваш запрос.\n\n"
                    f"Вам начислено ещё {amount} дополнительных скачиваний."
                ),
            )
            await query.edit_message_text(
                f"✅ Пользователю выдано +{amount}",
                reply_markup=None,
            )
        else:
            await query.edit_message_text("❌ Не удалось обработать запрос.", reply_markup=None)
      
    else:
        decline_bonus_request(request_id, ADMIN_ID)
        user_id = request[1]
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "❌ К сожалению, запрос отклонён.\n"
                "Попробуйте снова завтра или приобретите Premium."
            ),
        )
        await query.edit_message_text("❌ Запрос отклонён.", reply_markup=None)
