from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database.database import (
    get_user_profile,
    FREE_DAILY_LIMIT,
)


async def profile_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    profile = get_user_profile(update.effective_user.id)

    if profile is None:
        await update.message.reply_text(
            "❌ Профиль не найден."
        )
        return

    first_name, username, is_premium, premium_until, downloads_today = profile

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
    keyboard = [
        ["⭐ +10 скачиваний — 10⭐"],
        ["🔥 +30 скачиваний — 25⭐"],
        ["🚀 Безлимит на 24 часа — 50⭐"],
        ["👑 Premium 30 дней — 99⭐"],
        ["⬅️ Назад"],
    ]

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            is_persistent=True,
        ),
    )