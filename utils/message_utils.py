from telegram import Update


def get_message_target(update: Update):
    if update is None:
        return None

    message = getattr(update, "message", None)
    if message is not None:
        return message

    callback_query = getattr(update, "callback_query", None)
    if callback_query is not None:
        return callback_query.message

    return None
