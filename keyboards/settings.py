from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from utils.i18n import translate


def settings_keyboard(settings):
    language = settings["language"]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(translate(language, "settings_format"), callback_data="settings:format")],
        [InlineKeyboardButton(translate(language, "settings_history"), callback_data="settings:history")],
        [InlineKeyboardButton(translate(language, "settings_language"), callback_data="settings:language")],
    ])


def format_keyboard(language):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(translate(language, "format_video"), callback_data="settings:format:video")],
        [InlineKeyboardButton(translate(language, "format_document"), callback_data="settings:format:document")],
        [InlineKeyboardButton(translate(language, "back"), callback_data="settings:home")],
    ])


def history_keyboard(language):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(translate(language, "history_on"), callback_data="settings:history:on")],
        [InlineKeyboardButton(translate(language, "history_off"), callback_data="settings:history:off")],
        [InlineKeyboardButton(translate(language, "clear_history"), callback_data="settings:history:clear")],
        [InlineKeyboardButton(translate(language, "back"), callback_data="settings:home")],
    ])


def language_keyboard(language):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Русский", callback_data="settings:language:ru")],
        [InlineKeyboardButton("O'zbek", callback_data="settings:language:uz")],
        [InlineKeyboardButton("English", callback_data="settings:language:en")],
        [InlineKeyboardButton(translate(language, "back"), callback_data="settings:home")],
    ])


def confirm_clear_keyboard(language):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(translate(language, "confirm"), callback_data="settings:history:clear:yes")],
        [InlineKeyboardButton(translate(language, "cancel"), callback_data="settings:home")],
    ])
