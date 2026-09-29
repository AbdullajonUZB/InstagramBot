from pathlib import Path

from telegram import InputFile, Update
from telegram.ext import ContextTypes

from keyboards.main_menu import main_menu
from database.database import get_user_settings
from utils.i18n import translate
from utils.message_utils import require_effective_user, require_message_target
from utils.admin_roles import is_admin
from utils.chat_cleanup import clear_ui_messages, delete_button_message, delete_message_safely, remember_ui_message


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = require_effective_user(update)
    language = get_user_settings(user.id)["language"]

    message = require_message_target(update)
    await clear_ui_messages(
        context,
        message.chat_id,
        keep_ids=(message.message_id,) if update.callback_query else (),
    )
    banner_path = Path(__file__).resolve().parent.parent / "assets" / "welcome_banner.png"

    if banner_path.exists():
        with banner_path.open("rb") as banner:
            send_photo = context.bot.send_photo if update.callback_query else message.reply_photo
            send_kwargs = {"chat_id": message.chat_id} if update.callback_query else {}
            sent = await send_photo(
                photo=InputFile(banner, filename="welcome_banner.png"),
                caption=translate(language, "welcome"),
                reply_markup=main_menu(language, include_admin=is_admin(user.id)),
                **send_kwargs,
            )
    else:
        if update.callback_query:
            sent = await context.bot.send_message(
                chat_id=message.chat_id,
                text=translate(language, "welcome"),
                reply_markup=main_menu(language, include_admin=is_admin(user.id)),
            )
        else:
            sent = await message.reply_text(
                translate(language, "welcome"),
                reply_markup=main_menu(language, include_admin=is_admin(user.id)),
            )
    remember_ui_message(context, sent)

    if update.message is not None and update.message.text and update.message.text.startswith("/"):
        await delete_button_message(update.message)
    elif update.callback_query is not None:
        await delete_message_safely(message)


async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    await start(update, context)
