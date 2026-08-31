from telegram import ReplyKeyboardMarkup

from utils.i18n import translate
from services import SERVICES

def main_menu(language="ru", include_admin: bool = False):

    keyboard = [
        [
            translate(language, "download"),
            "👤 Профиль",
        ],
        [
            "🎵 Видео → MP3",
        ],
        [
            translate(language, "history"),
            translate(language, "settings"),
        ],
        [
            translate(language, "help"),
            "💎 Купить Premium",
        ],
    ]
    if include_admin:
        keyboard.insert(1, ["🛠 Админ-панель"])

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        is_persistent=True,
    )
from services import SERVICES


def service_menu(language="ru"):

    keyboard = []

    row = []

    for service in SERVICES.values():
        row.append(service["button"])

        if len(row) == 2:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    keyboard.append([translate(language, "back")])

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        is_persistent=True,
    )
def premium_menu():

    keyboard = [
        ["⭐ +20 скачиваний — 10⭐"],
        ["🔥 +30 скачиваний — 25⭐"],
        ["🚀 Безлимит на 24 часа — 50⭐"],
        ["👑 Premium 30 дней — 99⭐"],
        ["⬅️ Назад"],
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        is_persistent=True,
    )
