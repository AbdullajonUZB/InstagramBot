from telegram import Update
from telegram.ext import ContextTypes

import sqlite3

from config import ADMIN_ID
from database.database import add_security_log
from database.database import get_user_settings
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
