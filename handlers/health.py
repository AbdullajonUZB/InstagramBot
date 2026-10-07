import shutil
import time
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from database.database import get_admin_stats
from utils.message_utils import require_effective_user, require_message_target
from utils.admin_roles import is_admin
from utils.health_checks import collect_service_pings, format_service_ping
from utils.bot_profile import format_uptime


async def health_report_text(application=None):
    db_status = "✅" if Path("database/history.db").exists() else "⚠️"
    ffmpeg_status = "✅" if (shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")) else "❌"
    cookies_status = "✅" if Path("cookies.txt").exists() else "⚠️"
    stats = get_admin_stats()
    pings = await collect_service_pings()
    bot_data = application.bot_data if application is not None else {}
    started_at = bot_data.get("started_at")
    started_monotonic = bot_data.get("started_monotonic")
    uptime = format_uptime(time.monotonic() - started_monotonic) if started_monotonic else "неизвестно"
    started_label = started_at.strftime("%d.%m.%Y %H:%M:%S %Z") if started_at else "неизвестно"
    active_downloads = bot_data.get("download_active", 0)
    waiting_downloads = len(bot_data.get("download_queue_waiting", {}))

    text = (
        "🩺 Состояние бота и сервера\n\n"
        f"🖥 Домашний сервер: запущен · работает {uptime}\n"
        f"🕒 Запущен: {started_label}\n"
        "🤖 Приложение бота: работает\n"
        f"📥 Загрузки: выполняется {active_downloads} · в очереди {waiting_downloads}\n"
        f"🗄 База данных: {db_status}\n"
        f"🎞 FFmpeg: {ffmpeg_status}\n"
        f"🍪 Cookies: {cookies_status}\n\n"
        "📡 Проверка соединения до сервисов:\n"
        + "\n".join(format_service_ping(name, latency) for name, latency in pings)
        + "\n\n"
        f"👥 Пользователей: {stats['users']}\n"
        f"📥 Скачиваний сегодня: {stats['downloads_today']}"
    )
    return text


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(require_effective_user(update).id):
        return

    await require_message_target(update).reply_text(await health_report_text(context.application))
