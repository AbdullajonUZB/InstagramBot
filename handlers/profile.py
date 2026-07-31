from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database.database import (
    FREE_DAILY_LIMIT,
    get_user_profile,
    get_user_total_downloads,
)
from utils.message_utils import get_message_target


async def profile_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    profile = get_user_profile(update.effective_user.id)

    if profile is None:
        message = get_message_target(update)
        await message.reply_text(
            "❌ Профиль не найден."
        )
        return

    profile_values = profile if isinstance(profile, tuple) else ()
    if len(profile_values) >= 7:
        first_name, username, is_premium, premium_until, downloads_today, registered_at, bonus_downloads_total = profile_values[:7]
    else:
        first_name, username, is_premium, premium_until, downloads_today = profile_values[:5]
        registered_at = None
        bonus_downloads_total = 0

    total_downloads = get_user_total_downloads(update.effective_user.id)

    if is_premium:
        status = "👑 Premium"
        remaining = "♾ Безлимит"
    else:
        status = "🆓 Бесплатный"
        remaining = max(0, FREE_DAILY_LIMIT - downloads_today)

    text = (
        f"👤 <b>Ваш профиль</b>\n\n"
        f"🆔 <code>{update.effective_user.id}</code>\n"
        f"👤 Имя: {first_name}\n"
        f"📛 Username: @{username if username else '-'}\n\n"
        f"⭐ Статус: {status}\n"
        f"📥 Использовано сегодня: {downloads_today}/{FREE_DAILY_LIMIT}\n"
        f"📊 Осталось: {remaining}\n"
    )

    if premium_until:
        text += f"\n📅 Premium до: {premium_until}"

    if registered_at:
        text += f"\n📅 Дата регистрации: {registered_at}"

    text += f"\n📈 Всего скачиваний: {total_downloads}"
    text += f"\n🎁 Дополнительных скачиваний выдано: {bonus_downloads_total}"

    keyboard = [
        ["⭐ +10 скачиваний — 10⭐"],
        ["🔥 +30 скачиваний — 25⭐"],
        ["🚀 Безлимит на 24 часа — 50⭐"],
        ["👑 Premium 30 дней — 99⭐"],
        ["⬅️ Назад"],
    ]

    message = get_message_target(update)
    await message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            is_persistent=True,
        ),
    )