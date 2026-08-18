import asyncio

from telegram.error import NetworkError, TimedOut


async def reply_text_with_retry(message, *args, attempts: int = 3, **kwargs):
    """Reply to a message again when Telegram briefly drops the connection."""
    for attempt in range(attempts):
        try:
            return await message.reply_text(*args, **kwargs)
        except (NetworkError, TimedOut):
            if attempt == attempts - 1:
                raise
            await asyncio.sleep(1.5 * (attempt + 1))
