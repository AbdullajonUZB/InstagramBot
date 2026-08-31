from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.ext import ContextTypes

from keyboards.main_menu import main_menu
from database.database import get_user_settings
from utils.i18n import translate
from utils.message_utils import require_effective_user, require_message_target
from utils.admin_roles import is_admin


def admin_entry_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🛠 Админ-панель", callback_data="admin_open_panel")]]
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = require_effective_user(update)
    language = get_user_settings(user.id)["language"]

    message = require_message_target(update)
    banner_path = Path(__file__).resolve().parent.parent / "assets" / "welcome_banner.png"

    if banner_path.exists():
        with banner_path.open("rb") as banner:
            await message.reply_photo(
                photo=InputFile(banner, filename="welcome_banner.png"),
                caption=translate(language, "welcome"),
                reply_markup=main_menu(language, include_admin=is_admin(user.id)),
            )
    else:
        await message.reply_text(
            translate(language, "welcome"),
            reply_markup=main_menu(language, include_admin=is_admin(user.id)),
        )

    if is_admin(require_effective_user(update).id):
        await message.reply_text(
            "🛠 Управление ботом:",
            reply_markup=admin_entry_keyboard(),
        )


async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    await start(update, context)
