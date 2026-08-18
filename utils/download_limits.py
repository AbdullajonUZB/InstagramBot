from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update

from database.database import can_download, register_user
from utils.message_utils import get_message_target


async def ensure_download_allowed(update: Update) -> bool:
    """Register the user and show the limit prompt when no quota remains."""
    user = update.effective_user
    register_user(user.id, user.username, user.first_name)

    if can_download(user.id):
        return True

    message = get_message_target(update)
    if message is not None:
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("⭐ Купить Premium", callback_data="premium_stub")],
                [InlineKeyboardButton("🎁 Запросить дополнительные скачивания", callback_data="bonus_request")],
            ]
        )
        await message.reply_text(
            "🚫 Вы использовали все бесплатные скачивания на сегодня.\n\n"
            "Следующий лимит будет доступен после наступления нового дня.\n\n"
            "Вы можете:\n\n"
            "⭐ Купить Premium\n"
            "🎁 Запросить дополнительные скачивания",
            reply_markup=keyboard,
        )
    return False
