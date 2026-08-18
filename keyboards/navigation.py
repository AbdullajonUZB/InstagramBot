from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def back_to_main_menu_keyboard():
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu"),
            InlineKeyboardButton("🗑 Удалить", callback_data="delete_message"),
        ]]
    )


async def delete_message_callback(update, context):
    query = update.callback_query
    await query.answer()
    try:
        await query.message.delete()
    except Exception:
        await query.edit_message_reply_markup(reply_markup=None)
