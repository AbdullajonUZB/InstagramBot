from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database.database import (
    FREE_DAILY_LIMIT,
    get_user_profile,
    get_user_total_downloads,
    get_referral_stats,
)
from utils.message_utils import require_effective_user, require_message_target
from utils.chat_cleanup import remember_ui_message


async def profile_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user_id = require_effective_user(update).id
    message = require_message_target(update)
    profile = get_user_profile(user_id)

    if profile is None:
        await message.reply_text(
            "❌ Профиль не найден."
        )
        return

    profile_values = profile if isinstance(profile, tuple) else ()
    if len(profile_values) >= 8:
        first_name, username, is_premium, premium_until, downloads_today, registered_at, bonus_downloads_total, bonus_remaining = profile_values[:8]
    else:
        first_name, username, is_premium, premium_until, downloads_today = profile_values[:5]
        registered_at = None
        bonus_downloads_total = 0
        bonus_remaining = 0

    total_downloads = get_user_total_downloads(user_id)

    if is_premium:
        status = "👑 Premium"
        remaining = "♾ Безлимит"
    else:
        status = "🆓 Бесплатный"
        remaining = max(0, FREE_DAILY_LIMIT - downloads_today)

    text = (
        f"👤 <b>Ваш профиль</b>\n\n"
        f"🆔 <code>{user_id}</code>\n"
        f"👤 Имя: {first_name}\n"
        f"📛 Username: @{username if username else '-'}\n\n"
        f"⭐ Статус: {status}\n"
        f"📥 Использовано сегодня: {downloads_today}/{FREE_DAILY_LIMIT}\n"
        f"📊 Осталось сегодня: {remaining}"
        + (f" + 🎁 {bonus_remaining} бонусных" if bonus_remaining else "")
        + "\n"
    )

    if premium_until:
        text += f"\n📅 Premium до: {premium_until}"

    if registered_at:
        text += f"\n📅 Дата регистрации: {registered_at}"

    text += f"\n📈 Всего скачиваний: {total_downloads}"
    text += f"\n🎁 Дополнительных скачиваний выдано: {bonus_downloads_total}"
    invited, qualified, _ = get_referral_stats(user_id)
    text += f"\n👥 Приглашено друзей: {invited} (скачали: {qualified})"

    try:
        bot_username = (await context.bot.get_me()).username
        if bot_username:
            text += f"\n\n🔗 Ваша ссылка-приглашение:\nhttps://t.me/{bot_username}?start=ref_{user_id}"
            text += "\n🎁 За первую успешную загрузку приглашённого вы получите +5 скачиваний."
    except Exception:
        pass

    keyboard = [
        ["⭐ +20 скачиваний — 10⭐"],
        ["🔥 +30 скачиваний — 25⭐"],
        ["🚀 Безлимит на 24 часа — 50⭐"],
        ["👑 Premium 30 дней — 99⭐"],
        ["⬅️ Назад"],
    ]
    sent = await message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            is_persistent=True,
        ),
    )
    remember_ui_message(context, sent)
