"""Delete stale bot screens and temporary menu-button messages."""

from telegram import Message
from telegram.error import TelegramError


UI_MESSAGE_IDS_KEY = "chat_ui_message_ids"


def remember_ui_message(context, message: Message | None):
    if message is None:
        return
    message_ids = context.user_data.setdefault(UI_MESSAGE_IDS_KEY, [])
    reference = (message.chat_id, message.message_id)
    if reference not in message_ids:
        message_ids.append(reference)
    # Keep the cleanup list bounded even if Telegram rejects old deletions.
    del message_ids[:-20]


async def clear_ui_messages(context, chat_id: int, keep_ids=()):
    message_ids = context.user_data.pop(UI_MESSAGE_IDS_KEY, [])
    keep_ids = {(chat_id, message_id) for message_id in keep_ids}
    retained_ids = []
    for reference in message_ids:
        target_chat_id, message_id = reference
        if target_chat_id != chat_id:
            retained_ids.append(reference)
            continue
        if reference in keep_ids:
            retained_ids.append(reference)
            continue
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except TelegramError:
            # Already deleted, too old, or inaccessible: continue cleaning others.
            pass
    if retained_ids:
        context.user_data[UI_MESSAGE_IDS_KEY] = retained_ids


async def delete_button_message(message: Message | None):
    if message is None or not message.text:
        return
    await delete_message_safely(message)


async def delete_message_safely(message: Message | None):
    if message is None:
        return
    try:
        await message.delete()
    except TelegramError:
        pass
