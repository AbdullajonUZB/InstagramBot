import shutil
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from database.database import get_admin_stats
from utils.message_utils import require_effective_user, require_message_target
from utils.admin_roles import is_admin


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(require_effective_user(update).id):
        return

    db_status = "✅" if Path("database/history.db").exists() else "⚠️"
    ffmpeg_status = "✅" if (shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")) else "❌"
    cookies_status = "✅" if Path("cookies.txt").exists() else "⚠️"
    stats = get_admin_stats()

    await require_message_target(update).reply_text(
        "🩺 Состояние бота\n\n"
        f"🗄 База данных: {db_status}\n"
        f"🎞 FFmpeg: {ffmpeg_status}\n"
        f"🍪 Cookies: {cookies_status}\n"
        "📡 Polling: активен\n\n"
        f"👥 Пользователей: {stats['users']}\n"
        f"📥 Скачиваний сегодня: {stats['downloads_today']}"
    )
