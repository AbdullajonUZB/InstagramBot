from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import ADMIN_ID
from database.database import has_feedback, save_feedback_comment, save_feedback_rating


def feedback_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{rating}⭐", callback_data=f"feedback:rating:{rating}") for rating in range(1, 6)],
        [InlineKeyboardButton("Пропустить", callback_data="feedback:skip")],
    ])


async def ask_for_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user and not has_feedback(user.id):
        message = update.effective_message
        await message.reply_text(
            "⭐ Оцените работу бота\n\nНасколько удобно было скачать файл?",
            reply_markup=feedback_keyboard(),
        )


async def feedback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    if query.data.endswith(":skip"):
        await query.edit_message_text("Хорошо, спасибо за использование бота!")
        return

    rating = int(query.data.rsplit(":", 1)[1])
    save_feedback_rating(user.id, rating)
    context.user_data["awaiting_feedback_comment"] = True
    await context.bot.send_message(
        ADMIN_ID,
        f"⭐ Новая оценка: {rating}/5\n👤 {user.first_name or '-'} (@{user.username or 'без username'}, id={user.id})",
    )
    await query.edit_message_text(
        "Спасибо за оценку! 💛\n\nЕсли хотите, напишите пару слов — это поможет улучшить бота."
    )


async def handle_feedback_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.pop("awaiting_feedback_comment", False):
        return False
    user = update.effective_user
    comment = update.effective_message.text.strip()
    if comment:
        save_feedback_comment(user.id, comment)
        await context.bot.send_message(
            ADMIN_ID,
            f"💬 Комментарий к оценке\n👤 {user.first_name or '-'} (id={user.id})\n\n{comment[:3000]}",
        )
    await update.effective_message.reply_text("Спасибо за отзыв! Он уже отправлен администратору 🙌")
    return True
