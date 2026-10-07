import re
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import downloaders.instagram
import downloaders.pinterest
import downloaders.youtube
from downloaders.instagram import is_instagram_story_url
from keyboards.main_menu import service_menu
from keyboards.navigation import back_to_main_menu_keyboard
from database.database import get_user_settings
from utils.i18n import translate
from services import SERVICES, extract_service_link
from utils.message_utils import require_effective_user, require_message_target
from utils.user_locks import get_user_lock
from utils.followup_media import clear_followup_media
from utils.media_converter import convert_video_to_mp3
from utils.admin_notify import notify_admin_user_message
from handlers.feedback import ask_for_feedback, handle_feedback_comment
from database.database import add_history, increase_download_count
from utils.media_cache import make_cache_key, send_cached_media
from utils.download_audit import audit_successful_download
from utils.chat_cleanup import delete_message_safely
from utils.download_queue import run_queued_download
from utils.download_limits import ensure_download_allowed


def download_actions_keyboard(can_convert=False):
    first_row = []
    if can_convert:
        first_row.append(InlineKeyboardButton("🎵 Скачать как MP3", callback_data="download_ui:mp3"))
    first_row.append(InlineKeyboardButton("📥 Скачать ещё", callback_data="download_ui:again"))
    return InlineKeyboardMarkup(
        [
            first_row,
            [InlineKeyboardButton("⬅️ В меню", callback_data="download_ui:close")],
        ]
    )


def youtube_choice_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎥 Видео", callback_data="youtube_select:video"),
            InlineKeyboardButton("🎵 Музыка (MP3)", callback_data="youtube_select:audio"),
        ],
        [InlineKeyboardButton("⚙️ Выбрать качество", callback_data="youtube_quality:menu")],
        [InlineKeyboardButton("⬅️ В меню", callback_data="main_menu")],
    ])


async def delete_download_prompt(update, context):
    message_id = context.user_data.pop("download_prompt_message_id", None)
    message = require_message_target(update)
    if message_id is None or message is None:
        return

    try:
        await context.bot.delete_message(chat_id=message.chat_id, message_id=message_id)
    except Exception:
        pass

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = require_message_target(update)
    if not message.text:
        return

    if context.user_data.get("admin_management_action") == "add":
        from handlers.admin import handle_admin_management_message

        await handle_admin_management_message(update, context)
        return

    text = message.text.strip()
    user = require_effective_user(update)
    lock = await get_user_lock(context, user.id)
    async with lock:
        await _handle_message_locked(update, context, message, text)


async def _handle_message_locked(update, context, message, text):
    if await handle_feedback_comment(update, context):
        return
    language = get_user_settings(require_effective_user(update).id)["language"]

    selected_service = context.user_data.get("selected_service")
    detected_service, detected_url = extract_service_link(text)
    if detected_service:
        selected_service = detected_service
        url = detected_url
    elif "tiktok.com" in text.lower():
        await message.reply_text(translate(language, "unsupported_tiktok"))
        return
    elif not selected_service:
        try:
            await notify_admin_user_message(context, update, text)
        except Exception:
            pass
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
            await message.reply_text(
                translate(language, "wrong_service_link", service=service_name)
            )
            return
        url = match.group(1).rstrip(".,!?;:)]}")

    if not url:
        await message.reply_text(
            translate(language, "wrong_service_link", service=service_name)
        )
        return

    if selected_service != "youtube":
        if not await ensure_download_allowed(update):
            return
        cached_message = await send_cached_media(update, make_cache_key(url, selected_service), context)
        if cached_message is not None:
            add_history(require_effective_user(update).id, url, f"{selected_service} (кэш)")
            increase_download_count(require_effective_user(update).id)
            await delete_download_prompt(update, context)
            await message.reply_text(
                "⚡ Файл найден в кэше. Что сделать дальше?",
                reply_markup=download_actions_keyboard(False),
            )
            return

    if selected_service == "youtube":
        context.user_data["pending_youtube_url"] = url
        await message.reply_text(
            "🎬 Что вы хотите скачать?",
            reply_markup=youtube_choice_keyboard(),
        )
        return

    if selected_service == "instagram" and is_instagram_story_url(url):
        context.user_data["pending_instagram_story_url"] = url
        await message.reply_text(
            "📖 Что скачать из Instagram Stories?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📥 Эта история", callback_data="instagram_story:one")],
                [InlineKeyboardButton("📚 Все истории", callback_data="instagram_story:all")],
                [InlineKeyboardButton("🎬 Только видео", callback_data="instagram_story:video")],
                [InlineKeyboardButton("⬅️ В меню", callback_data="main_menu")],
            ]),
        )
        return

    clear_followup_media(context)
    status_message = await message.reply_text(
        translate(language, "downloading")
    )

    success = await run_queued_download(
        context,
        status_message,
        downloader(update, context, url),
        owner_id=require_effective_user(update).id,
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
    if query is None or not query.message:
        return
    message = require_message_target(update)
    await query.answer()

    if not query.data:
        return

    choice = query.data.split(":", 1)[1]
    lock = await get_user_lock(context, require_effective_user(update).id)
    async with lock:
        pending_url = context.user_data.get("pending_youtube_url")
        if not pending_url:
            await message.reply_text("⚠️ Ссылка для YouTube была потеряна. Попробуйте отправить её ещё раз.")
            return

        context.user_data.pop("pending_youtube_url", None)
        clear_followup_media(context)
        cache_variant = "youtube:audio" if choice == "audio" else "youtube:video:auto"
        if not await ensure_download_allowed(update):
            return
        cached_message = await send_cached_media(update, make_cache_key(pending_url, cache_variant), context)
        if cached_message is not None:
            add_history(require_effective_user(update).id, pending_url, f"YouTube {'аудио' if choice == 'audio' else 'видео'} (кэш)")
            increase_download_count(require_effective_user(update).id)
            await message.reply_text("⚡ Файл найден в кэше. Что сделать дальше?", reply_markup=download_actions_keyboard(False))
            await delete_message_safely(query.message)
            return
        status_message = await message.reply_text("⏳ Скачивание началось...")

        try:
            success = await run_queued_download(
                context,
                status_message,
                downloaders.youtube.download_youtube(
                    update, context, pending_url, choice=choice
                ),
                owner_id=require_effective_user(update).id,
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
            await message.reply_text("⚠️ Не удалось отправить файл в Telegram. Попробуйте ещё раз.")
        elif success is True:
            await delete_download_prompt(update, context)
            await message.reply_text(
                "✅ Готово. Что сделать дальше?",
                reply_markup=download_actions_keyboard(
                    bool(context.user_data.get("followup_media_path"))
                ),
            )
            await ask_for_feedback(update, context)
            await delete_message_safely(query.message)


async def handle_youtube_quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None or not query.message or not query.data:
        return
    await query.answer()
    action = query.data.split(":", 1)[1]
    if action == "menu":
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚡ Авто", callback_data="youtube_quality:auto")],
                [InlineKeyboardButton("🎞 720p", callback_data="youtube_quality:720"),
                 InlineKeyboardButton("🎞 480p", callback_data="youtube_quality:480")],
                [InlineKeyboardButton("🖼 Оригинал", callback_data="youtube_quality:original")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="youtube_quality:back")],
            ])
        )
        return

    if action == "back":
        await query.edit_message_text(
            "🎬 Что вы хотите скачать?",
            reply_markup=youtube_choice_keyboard(),
        )
        return

    quality = action
    pending_url = context.user_data.get("pending_youtube_url")
    if not pending_url or quality not in {"auto", "720", "480", "original"}:
        await query.message.reply_text("⚠️ Ссылка для YouTube была потеряна. Отправьте её ещё раз.")
        return

    lock = await get_user_lock(context, require_effective_user(update).id)
    async with lock:
        context.user_data.pop("pending_youtube_url", None)
        clear_followup_media(context)
        message = require_message_target(update)
        if not await ensure_download_allowed(update):
            return
        cached_message = await send_cached_media(
            update, make_cache_key(pending_url, f"youtube:video:{quality}"), context
        )
        if cached_message is not None:
            add_history(require_effective_user(update).id, pending_url, "YouTube видео (кэш)")
            increase_download_count(require_effective_user(update).id)
            await message.reply_text("⚡ Файл найден в кэше. Что сделать дальше?", reply_markup=download_actions_keyboard(False))
            await delete_message_safely(query.message)
            return
        status_message = await message.reply_text("⏳ Скачивание началось...")
        try:
            success = await run_queued_download(
                context,
                status_message,
                downloaders.youtube.download_youtube(
                    update, context, pending_url, choice="video", quality=quality
                ),
                owner_id=require_effective_user(update).id,
            )
        finally:
            try:
                await status_message.delete()
            except Exception:
                pass
        if success is True:
            await delete_download_prompt(update, context)
            await message.reply_text(
                "✅ Готово. Что сделать дальше?",
                reply_markup=download_actions_keyboard(bool(context.user_data.get("followup_media_path"))),
            )
            await ask_for_feedback(update, context)
            await delete_message_safely(query.message)


async def handle_instagram_story_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None or not query.message or not query.data:
        return
    await query.answer()
    mode = query.data.split(":", 1)[1]
    url = context.user_data.pop("pending_instagram_story_url", None)
    if not url or mode not in {"one", "all", "video"}:
        await query.message.reply_text("⚠️ Ссылка на Story была потеряна. Отправьте её ещё раз.")
        return

    user_id = require_effective_user(update).id
    lock = await get_user_lock(context, user_id)
    async with lock:
        clear_followup_media(context)
        message = require_message_target(update)
        status_message = await message.reply_text("⏳ Скачивание Story началось...")
        try:
            success = await run_queued_download(
                context,
                status_message,
                downloaders.instagram.download_instagram(
                    update, context, url, story_mode=mode
                ),
                owner_id=user_id,
            )
        finally:
            try:
                await status_message.delete()
            except Exception:
                pass
        if success is True:
            await delete_download_prompt(update, context)
            await message.reply_text(
                "✅ Готово. Что сделать дальше?",
                reply_markup=download_actions_keyboard(bool(context.user_data.get("followup_media_path"))),
            )
            await ask_for_feedback(update, context)
            await delete_message_safely(query.message)


async def handle_download_ui_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None or not query.data:
        return
    message = require_message_target(update)

    await query.answer()
    action = query.data.split(":", 1)[1]

    if action == "mp3":
        input_path = context.user_data.get("followup_media_path")
        media_dir = context.user_data.get("followup_media_dir")
        if not input_path or not Path(input_path).exists():
            await message.reply_text("⚠️ Видео для конвертации больше недоступно. Отправьте ссылку заново.")
            clear_followup_media(context)
            return

        output_path = Path(media_dir) / "audio.mp3"
        try:
            await convert_video_to_mp3(Path(input_path), output_path)
            with output_path.open("rb") as audio:
                sent_message = await message.reply_audio(
                    audio=audio,
                    filename="audio.mp3",
                    title="audio",
                    read_timeout=600,
                    write_timeout=600,
                    connect_timeout=60,
                    pool_timeout=60,
                )
            await audit_successful_download(
                context,
                update,
                context.user_data.get("followup_media_url", "Источник не сохранён"),
                "MP3-конвертация",
                sent_message,
            )
            clear_followup_media(context)
            await query.edit_message_text(
                "✅ MP3 готов.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ В меню", callback_data="main_menu")
                ]]),
            )
        except Exception as exc:
            await message.reply_text(f"❌ Не удалось создать MP3: {exc}")
    elif action == "again":
        await query.edit_message_text(
            "🔗 Отправьте ссылку на видео или публикацию.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ В меню", callback_data="main_menu")
            ]]),
        )
        context.user_data["download_prompt_message_id"] = query.message.message_id
    elif action == "close":
        clear_followup_media(context)
        await message.delete()
        from handlers.start import start

        await start(update, context)
