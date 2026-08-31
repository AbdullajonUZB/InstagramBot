from config import ADMIN_ID
from database.database import get_bot_admins, is_bot_admin


ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"
ROLE_USER = "user"


def get_role(telegram_id: int) -> str:
    if telegram_id == ADMIN_ID:
        return ROLE_OWNER
    if is_bot_admin(telegram_id):
        return ROLE_ADMIN
    return ROLE_USER


def is_admin(telegram_id: int) -> bool:
    return get_role(telegram_id) in {ROLE_OWNER, ROLE_ADMIN}


def is_owner(telegram_id: int) -> bool:
    return telegram_id == ADMIN_ID


def get_all_admin_ids() -> list[int]:
    return [ADMIN_ID, *(int(row[0]) for row in get_bot_admins())]
