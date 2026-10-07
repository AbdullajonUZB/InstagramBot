from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import ADMIN_ID
from database.database import has_feedback, save_feedback_comment, save_feedback_rating
from utils.message_utils import require_effective_user, require_message_target


def feedback_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{rating}⭐", callback_data=f"feedback:rating:{rating}") for rating in range(1, 6)],
        [InlineKeyboardButton("Пропустить", callback_data="feedback:skip")],
        [InlineKeyboardButton("⬅️ В меню", callback_data="feedback:home")],
    ])


async def ask_for_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = require_effective_user(update)
    if not has_feedback(user.id):
        message = require_message_target(update)
        await message.reply_text(
            "⭐ Оцените работу бота\n\nНасколько удобно было скачать файл?",
            reply_markup=feedback_keyboard(),
        )


async def feedback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None or not query.data:
        return
    await query.answer()
    user = require_effective_user(update)
    if query.data == "feedback:home":
        if context.user_data is not None:
            context.user_data.pop("awaiting_feedback_comment", None)
        from handlers.start import start

        await start(update, context)
        return
    if query.data.endswith(":skip"):
        await query.edit_message_text(
            "Хорошо, спасибо за использование бота!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ В меню", callback_data="feedback:home")
            ]]),
        )
        return

    rating = int(query.data.rsplit(":", 1)[1])
    save_feedback_rating(user.id, rating)
    if context.user_data is not None:
        context.user_data["awaiting_feedback_comment"] = True
    await context.bot.send_message(
        ADMIN_ID,
        f"⭐ Новая оценка: {rating}/5\n👤 {user.first_name or '-'} (@{user.username or 'без username'}, id={user.id})",
    )
    await query.edit_message_text(
        "Спасибо за оценку! 💛\n\nЕсли хотите, напишите пару слов — это поможет улучшить бота.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ В меню", callback_data="feedback:home")
        ]]),
    )


async def handle_feedback_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data is None or not context.user_data.pop("awaiting_feedback_comment", False):
        return False
    user = require_effective_user(update)
    message = require_message_target(update)
    comment = (message.text or "").strip()
    if comment:
        save_feedback_comment(user.id, comment)
        await context.bot.send_message(
            ADMIN_ID,
            f"💬 Комментарий к оценке\n👤 {user.first_name or '-'} (id={user.id})\n\n{comment[:3000]}",
        )
    await message.reply_text(
        "Спасибо за отзыв! Он уже отправлен администратору 🙌",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ В меню", callback_data="main_menu")
        ]]),
    )
    return True
