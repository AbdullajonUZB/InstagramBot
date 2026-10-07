def format_uptime(seconds: float | int | None) -> str:
    if seconds is None:
        return "неизвестно"
    total = max(0, int(seconds))
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    if days:
        return f"{days} дн. {hours} ч. {minutes} мин."
    if hours:
        return f"{hours} ч. {minutes} мин."
    return f"{minutes} мин."
