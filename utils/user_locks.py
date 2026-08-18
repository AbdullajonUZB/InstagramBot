import asyncio


async def get_user_lock(context, user_id: int) -> asyncio.Lock:
    """Return a stable per-user lock stored in the application state."""
    locks = context.application.bot_data.setdefault("user_locks", {})
    return locks.setdefault(user_id, asyncio.Lock())
