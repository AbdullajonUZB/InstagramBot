import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, Forbidden, TelegramError

from config import REMINDER_AFTER_DAYS, REMINDER_BATCH_SIZE, REMINDER_INTERVAL_HOURS
from database.database import get_inactive_users, mark_reminder_sent, set_reminders_enabled

logger = logging.getLogger(__name__)


def reminder_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Скачать", callback_data="reminder:download")],
        [InlineKeyboardButton("🔕 Не напоминать", callback_data="reminder:disable")],
    ])


def _display_name(first_name, username):
    return (first_name or username or "друг").strip()[:64]


async def send_inactive_user_reminders(application):
    for telegram_id, first_name, username in get_inactive_users(REMINDER_AFTER_DAYS, REMINDER_BATCH_SIZE):
        text = (
            f"👋 {_display_name(first_name, username)}, мы по вам соскучились!\n\n"
            "Давно не скачивали видео, фото или музыку. "
            "Отправьте новую ссылку — я быстро подготовлю файл 😊"
        )
        try:
            await application.bot.send_message(chat_id=telegram_id, text=text, reply_markup=reminder_keyboard())
        except Forbidden as error:
            logger.info("Пользователь %s недоступен для напоминаний: %s", telegram_id, error)
            set_reminders_enabled(telegram_id, False)
        except (BadRequest, TelegramError) as error:
            logger.warning("Не удалось отправить напоминание пользователю %s: %s", telegram_id, error)
        else:
            mark_reminder_sent(telegram_id)


async def reminder_loop(application):
    await asyncio.sleep(60)
    while True:
        try:
            await send_inactive_user_reminders(application)
        except Exception:
            logger.exception("Ошибка фоновой рассылки напоминаний")
        await asyncio.sleep(max(1, REMINDER_INTERVAL_HOURS) * 3600)


async def reminder_post_init(application):
    application.bot_data["reminder_task"] = application.create_task(reminder_loop(application), name="inactive-user-reminders")


async def reminder_post_shutdown(application):
    task = application.bot_data.pop("reminder_task", None)
    if task is not None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
