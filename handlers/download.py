from multiprocessing import context
from pydoc import text
import re
from turtle import update

from telegram import Update
from telegram.ext import ContextTypes

import downloaders.instagram
import downloaders.pinterest
import downloaders.tiktok
import downloaders.youtube
from keyboards.main_menu import service_menu
from database.database import get_user_settings
from utils.i18n import translate
from services import SERVICES

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("========== DOWNLOAD.PY NEW VERSION ==========")
    print("DOWNLOAD:", update.message.text)
    print("user_data =", context.user_data)
    
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    language = get_user_settings(update.effective_user.id)["language"]

    selected_service = context.user_data.get("selected_service")
    print("selected_service =", selected_service)
    print("user_data =", context.user_data)
    if not selected_service:

        await update.message.reply_text(
            translate(language, "choose_first"),
            reply_markup=service_menu(language),
        )

        return

    service = SERVICES[selected_service]

    service_name = service["button"][2:]
    pattern = service["pattern"]
    downloader = service["downloader"]

    match = re.search(pattern, text)

    if not match:

        await update.message.reply_text(
            translate(language, "wrong_service_link", service=service_name)
        )

        return

    url = match.group(1)

    status_message = await update.message.reply_text(
        translate(language, "downloading")
    )

    success = await downloader(
        update,
        context,
        url
    )

    try:
        await status_message.delete()
    except Exception:
        pass

    if not success:

        await update.message.reply_text(
            translate(language, "download_failed")
        )
