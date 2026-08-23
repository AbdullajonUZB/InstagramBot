from typing import cast

from telegram import Message, Update, User


def get_message_target(update: Update) -> Message | None:
    if update is None:
        return None

    message = getattr(update, "message", None)
    if message is not None:
        return message

    callback_query = getattr(update, "callback_query", None)
    if callback_query is not None:
        return callback_query.message

    return None


def require_message_target(update: Update) -> Message:
    """Return a concrete Telegram message or fail before an API call."""
    message = get_message_target(update)
    if message is None:
        raise RuntimeError("Telegram update does not contain a message")
    return cast(Message, message)


def require_effective_user(update: Update) -> User:
    user = update.effective_user
    if user is None:
        raise RuntimeError("Telegram update does not contain a user")
    return user
