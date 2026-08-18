import re
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import downloaders.instagram
import downloaders.pinterest
import downloaders.tiktok
import downloaders.youtube
from keyboards.main_menu import service_menu
from keyboards.navigation import back_to_main_menu_keyboard
from database.database import get_user_settings
from utils.i18n import translate
from services import SERVICES, extract_service_link
from utils.message_utils import get_message_target
from utils.user_locks import get_user_lock
from utils.followup_media import clear_followup_media
from utils.media_converter import convert_video_to_mp3
from utils.admin_notify import notify_admin_user_message
from handlers.feedback import ask_for_feedback, handle_feedback_comment


def download_actions_keyboard(can_convert=False):
    first_row = []
    if can_convert:
        first_row.append(InlineKeyboardButton("🎵 Скачать как MP3", callback_data="download_ui:mp3"))
    first_row.append(InlineKeyboardButton("📥 Скачать ещё", callback_data="download_ui:again"))
    return InlineKeyboardMarkup(
        [
            first_row,
            [InlineKeyboardButton("❌ Закрыть", callback_data="download_ui:close")],
        ]
    )


async def delete_download_prompt(update, context):
    message_id = context.user_data.pop("download_prompt_message_id", None)
    message = get_message_target(update)
    if message_id is None or message is None:
        return

    try:
        await context.bot.delete_message(chat_id=message.chat_id, message_id=message_id)
    except Exception:
        pass

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = get_message_target(update)
    if not message or not getattr(message, "text", None):
        return

    text = message.text.strip()
    lock = await get_user_lock(context, update.effective_user.id)
    async with lock:
        await _handle_message_locked(update, context, message, text)


async def _handle_message_locked(update, context, message, text):
    if await handle_feedback_comment(update, context):
        return
    language = get_user_settings(update.effective_user.id)["language"]

    selected_service = context.user_data.get("selected_service")
    detected_service, detected_url = extract_service_link(text)
    if detected_service:
        selected_service = detected_service
        url = detected_url
    elif not selected_service:
        try:
            await notify_admin_user_message(context, update, text)
        except Exception:
            pass
        message = get_message_target(update)
        await message.reply_text(
            translate(language, "choose_first"),
            reply_markup=service_menu(language),
        )
        return

    service = SERVICES[selected_service]
    service_name = service["button"][2:]
    pattern = service["pattern"]
    downloader = service["downloader"]

    if detected_service:
        downloader = service["downloader"]
    else:
        match = re.search(pattern, text)
        if not match:
            try:
                await notify_admin_user_message(context, update, text)
            except Exception:
                pass
            message = get_message_target(update)
            await message.reply_text(
                translate(language, "wrong_service_link", service=service_name)
            )
            return
        url = match.group(1).rstrip(".,!?;:)]}")

    if not url:
        message = get_message_target(update)
        await message.reply_text(
            translate(language, "wrong_service_link", service=service_name)
        )
        return

    if selected_service == "youtube":
        context.user_data["pending_youtube_url"] = url
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🎥 Видео", callback_data="youtube_select:video"),
                    InlineKeyboardButton("🎵 Музыка (MP3)", callback_data="youtube_select:audio"),
                ]
            ]
        )
        message = get_message_target(update)
        await message.reply_text(
            "🎬 Что вы хотите скачать?",
            reply_markup=keyboard,
        )
        return

    message = get_message_target(update)
    clear_followup_media(context)
    status_message = await message.reply_text(
        translate(language, "downloading")
    )

    success = await downloader(
        update,
        context,
        url,
    )

    try:
        await status_message.delete()
    except Exception:
        pass

    if success is False:
        # Downloader already sent the specific error message and navigation.
        pass
    elif success is True:
        await delete_download_prompt(update, context)
        await message.reply_text(
            "✅ Готово. Что сделать дальше?",
            reply_markup=download_actions_keyboard(
                bool(context.user_data.get("followup_media_path"))
            ),
        )
        await ask_for_feedback(update, context)


async def handle_youtube_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not query.data:
        return

    choice = query.data.split(":", 1)[1]
    lock = await get_user_lock(context, update.effective_user.id)
    async with lock:
        pending_url = context.user_data.get("pending_youtube_url")
        if not pending_url:
            await query.message.reply_text("⚠️ Ссылка для YouTube была потеряна. Попробуйте отправить её ещё раз.")
            return

        context.user_data.pop("pending_youtube_url", None)
        clear_followup_media(context)
        status_message = await query.message.reply_text("⏳ Скачивание началось...")

        try:
            success = await downloaders.youtube.download_youtube(
                update,
                context,
                pending_url,
                choice=choice,
            )
        finally:
            try:
                await status_message.delete()
            except Exception:
                pass

        if success is False:
            # YouTube downloader already sent the specific error message.
            pass
        elif success is None:
            await query.message.reply_text("⚠️ Не удалось отправить файл в Telegram. Попробуйте ещё раз.")
        elif success is True:
            await delete_download_prompt(update, context)
            await query.message.reply_text(
                "✅ Готово. Что сделать дальше?",
                reply_markup=download_actions_keyboard(
                    bool(context.user_data.get("followup_media_path"))
                ),
            )
            await ask_for_feedback(update, context)


async def handle_download_ui_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None or not query.data:
        return

    await query.answer()
    action = query.data.split(":", 1)[1]

    if action == "mp3":
        input_path = context.user_data.get("followup_media_path")
        media_dir = context.user_data.get("followup_media_dir")
        if not input_path or not Path(input_path).exists():
            await query.message.reply_text("⚠️ Видео для конвертации больше недоступно. Отправьте ссылку заново.")
            clear_followup_media(context)
            return

        output_path = Path(media_dir) / "audio.mp3"
        try:
            await convert_video_to_mp3(Path(input_path), output_path)
            with output_path.open("rb") as audio:
                await query.message.reply_audio(
                    audio=audio,
                    filename="audio.mp3",
                    title="audio",
                    read_timeout=600,
                    write_timeout=600,
                    connect_timeout=60,
                    pool_timeout=60,
                )
            clear_followup_media(context)
            await query.edit_message_text("✅ MP3 готов.", reply_markup=None)
        except Exception as exc:
            await query.message.reply_text(f"❌ Не удалось создать MP3: {exc}")
    elif action == "again":
        prompt = await query.message.reply_text(
            "🔗 Отправьте ссылку на видео или публикацию."
        )
        context.user_data["download_prompt_message_id"] = prompt.message_id
    elif action == "close":
        clear_followup_media(context)
        await query.message.delete()
        from handlers.start import start

        await start(update, context)
