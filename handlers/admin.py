from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ApplicationHandlerStop, ContextTypes
from utils.message_utils import require_effective_user, require_message_target
import sqlite3

from config import ADMIN_ID
from database.database import (
    add_security_log,
    approve_bonus_request,
    create_bonus_download_request,
    decline_bonus_request,
    get_bonus_request,
    get_user_profile,
    get_user_settings,
    get_user_total_downloads,
    has_active_bonus_request,
    FREE_DAILY_LIMIT,
    get_admin_stats,
    ban_user,
    get_banned_users,
    unban_user,
    add_bot_admin,
    remove_bot_admin,
    get_bot_admins,
    get_download_stats_by_service,
    get_recent_users,
    get_recent_security_events,
    get_user_by_username,
    get_reminder_settings,
    update_bot_setting,
)
from utils.i18n import translate
from utils.admin_roles import is_admin, is_owner
from utils.maintenance import startup_checks


async def db(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = require_effective_user(update)
    language = get_user_settings(user.id)["language"]

    if not is_admin(user.id):

        add_security_log(
            user.id,
            user.username,
            user.first_name,
            "ACCESS_DENIED",
            "/db"
        )

        message = require_message_target(update)
        await message.reply_text(
            translate(language, "access_denied")
        )

        return

    conn = sqlite3.connect("database/history.db")

    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        username,
        media_type,
        status,
        created_at
    FROM downloads
    ORDER BY id DESC
    LIMIT 10
    """)

    rows = cursor.fetchall()

    conn.close()

    if not rows:

        message = require_message_target(update)
        await message.reply_text(
            translate(language, "admin_history_empty")
        )

        return

    text = translate(language, "admin_history_title")

    for row in rows:

        username = row[0] or "Без username"

        text += (
            f"👤 {username}\n"
            f"📂 {row[1]}\n"
            f"📌 {row[2]}\n"
            f"🕒 {row[3]}\n\n"
        )

    message = require_message_target(update)
    await message.reply_text(text)


async def admin_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(require_effective_user(update).id):
        return

    stats = get_admin_stats()
    await require_message_target(update).reply_text(
        "📊 Статус бота\n\n"
        f"👥 Пользователей: {stats['users']}\n"
        f"📥 Скачиваний сегодня: {stats['downloads_today']}\n"
        f"🗂 Записей истории сегодня: {stats['history_today']}\n"
        f"👑 Premium пользователей: {stats['premium_users']}"
    )


def admin_panel_keyboard(owner: bool = False):
    rows = [
        [
            InlineKeyboardButton("📊 Dashboard", callback_data="admin_panel:status"),
            InlineKeyboardButton("📈 Сервисы", callback_data="admin_panel:services"),
        ],
        [
            InlineKeyboardButton("👥 Пользователи", callback_data="admin_panel:users"),
            InlineKeyboardButton("🚫 Баны", callback_data="admin_panel:banned"),
        ],
        [InlineKeyboardButton("🛡 Безопасность", callback_data="admin_panel:security")],
        [InlineKeyboardButton("🩺 Здоровье", callback_data="admin_panel:health")],
        [InlineKeyboardButton("🔔 Напоминания", callback_data="admin_panel:reminders")],
        [InlineKeyboardButton("🔄 Обновить", callback_data="admin_panel:refresh")],
    ]
    if owner:
        rows.append([InlineKeyboardButton("👥 Администраторы", callback_data="admin_panel:admins")])
    return InlineKeyboardMarkup(rows)


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = require_effective_user(update).id
    if not is_admin(user_id):
        return
    await require_message_target(update).reply_text(
        "🛠 Админская панель\n\nВыберите действие:",
        reply_markup=admin_panel_keyboard(is_owner(user_id)),
    )


async def handle_admin_entry_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = require_effective_user(update).id
    if query is None or not is_admin(user_id):
        return
    await query.answer()
    await admin_panel(update, context)


async def handle_admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = require_effective_user(update).id
    if query is None or query.message is None or not is_admin(user_id):
        return
    await query.answer()
    if not query.data:
        return
    action = query.data.split(":", 1)[1]

    if action in {"status", "refresh"}:
        stats = get_admin_stats()
        text = (
            "🛠 Dashboard\n\n"
            f"👥 Пользователей: {stats['users']}\n"
            f"📥 Скачиваний сегодня: {stats['downloads_today']}\n"
            f"🗂 Истории сегодня: {stats['history_today']}\n"
            f"👑 Premium: {stats['premium_users']}"
        )
        try:
            await query.edit_message_text(text, reply_markup=admin_panel_keyboard(is_owner(user_id)))
        except BadRequest as error:
            if "message is not modified" not in str(error).lower():
                raise
    elif action == "banned":
        banned = get_banned_users()
        if not banned:
            text = "🚫 Заблокированных пользователей нет."
        else:
            text = "🚫 Заблокированные пользователи:\n\n" + "\n".join(
                f"• {user_id} — {reason or 'без причины'}"
                for user_id, reason, _ in banned
            )
        await query.edit_message_text(text[:4000], reply_markup=banned_users_keyboard(banned))
    elif action == "services":
        rows = get_download_stats_by_service()
        text = "📈 Скачивания по сервисам\n\n"
        text += "\n".join(f"• {media_type}: {count}" for media_type, count in rows) or "Данных пока нет."
        await query.edit_message_text(text[:4000], reply_markup=admin_panel_keyboard(is_owner(user_id)))
    elif action == "users":
        rows = get_recent_users()
        text = "👥 Последние пользователи\n\n"
        if rows:
            text += "\n".join(
                f"• {first_name or '-'} (@{username or '-'}, ID: {telegram_id})"
                f" — {'Premium' if is_premium else 'обычный'}, сегодня: {downloads_today}"
                for telegram_id, username, first_name, is_premium, downloads_today, _ in rows
            )
        else:
            text += "Пользователей пока нет."
        await query.edit_message_text(text[:4000], reply_markup=admin_panel_keyboard(is_owner(user_id)))
    elif action == "security":
        rows = get_recent_security_events()
        text = "🛡 Последние события безопасности\n\n"
        text += "\n".join(
            f"• {created_at} — {telegram_id or '-'} — {event or '-'} {details or ''}"
            for telegram_id, event, details, created_at in rows
        ) or "Событий пока нет."
        await query.edit_message_text(text[:4000], reply_markup=admin_panel_keyboard(is_owner(user_id)))
    elif action == "health":
        warnings = startup_checks()
        text = "🩺 Состояние бота\n\n✅ Приложение запущено\n"
        text += "\n".join(f"⚠️ {warning}" for warning in warnings) or "✅ Критических предупреждений нет."
        await query.edit_message_text(text[:4000], reply_markup=admin_panel_keyboard(is_owner(user_id)))
    elif action == "reminders" and is_owner(user_id):
        await query.edit_message_text(
            _reminders_text(), reply_markup=reminders_keyboard()
        )
    elif action == "admins" and is_owner(user_id):
        await query.edit_message_text(
            _admins_text(),
            reply_markup=admin_management_keyboard(),
        )


def _reminders_text() -> str:
    settings = get_reminder_settings()
    status = "включены" if settings["enabled"] else "выключены"
    return (
        "🔔 Напоминания пользователям\n\n"
        f"Статус: {status}\n"
        f"Период неактивности: {settings['after_days']} дн.\n"
        f"Отправлено всего: {settings['sent_total']}\n"
        f"Отправлено сегодня: {settings['sent_today']}"
    )


def reminders_keyboard():
    settings = get_reminder_settings()
    status_action = "off" if settings["enabled"] else "on"
    status_label = "🔕 Выключить" if settings["enabled"] else "🔔 Включить"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(status_label, callback_data=f"admin_reminders:{status_action}")],
        [InlineKeyboardButton("⏱ 3 дня", callback_data="admin_reminders:days:3"),
         InlineKeyboardButton("⏱ 7 дней", callback_data="admin_reminders:days:7"),
         InlineKeyboardButton("⏱ 14 дней", callback_data="admin_reminders:days:14")],
        [InlineKeyboardButton("⬅️ В админ-панель", callback_data="admin_panel:status")],
    ])


async def handle_admin_reminders_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = require_effective_user(update).id
    if query is None or not is_owner(user_id) or not query.data:
        return
    await query.answer()
    parts = query.data.split(":")
    if parts[1] == "on":
        update_bot_setting("reminders_enabled", 1)
    elif parts[1] == "off":
        update_bot_setting("reminders_enabled", 0)
    elif parts[1] == "days" and len(parts) == 3 and parts[2] in {"3", "7", "14"}:
        update_bot_setting("reminder_after_days", parts[2])
    await query.edit_message_text(_reminders_text(), reply_markup=reminders_keyboard())


def _admins_text() -> str:
    rows = get_bot_admins()
    if not rows:
        return "👥 Администраторы\n\nДополнительных администраторов пока нет."
    lines = ["👥 Администраторы\n", f"👑 Владелец: {ADMIN_ID}", ""]
    lines.extend(f"🛡 Администратор: {telegram_id}" for telegram_id, *_ in rows)
    return "\n".join(lines)


def admin_management_keyboard():
    rows = [[InlineKeyboardButton("➕ Добавить администратора", callback_data="admin_admins:add")]]
    for telegram_id, *_ in get_bot_admins():
        rows.append([
            InlineKeyboardButton(
                f"❌ Удалить {telegram_id}",
                callback_data=f"admin_admins:remove:{telegram_id}",
            )
        ])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="admin_admins:back")])
    return InlineKeyboardMarkup(rows)


def banned_users_keyboard(banned):
    rows = [
        [InlineKeyboardButton(
            f"✅ Разблокировать {telegram_id}",
            callback_data=f"admin_unban:{telegram_id}",
        )]
        for telegram_id, *_ in banned
    ]
    rows.append([InlineKeyboardButton("⬅️ В админ-панель", callback_data="admin_panel:status")])
    return InlineKeyboardMarkup(rows)


async def handle_admin_management_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = require_effective_user(update).id
    if query is None or query.message is None or not is_owner(user_id) or not query.data:
        return
    await query.answer()
    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "add":
        context.user_data["admin_management_action"] = "add"
        await query.message.reply_text(
            "➕ Отправьте @username пользователя, которого нужно сделать администратором.\n"
            "Пользователь должен сначала запустить бота."
        )
    elif action == "confirm_add" and len(parts) == 3 and parts[2].isdigit():
        new_admin_id = int(parts[2])
        if context.user_data.get("pending_admin") != new_admin_id:
            await query.answer("Запрос уже устарел.", show_alert=True)
            return
        if add_bot_admin(new_admin_id, user_id):
            context.user_data.pop("pending_admin", None)
            await query.edit_message_text(
                f"✅ Пользователь {new_admin_id} добавлен как администратор.",
                reply_markup=admin_management_keyboard(),
            )
        else:
            await query.edit_message_text(
                "ℹ️ Этот пользователь уже является администратором.",
                reply_markup=admin_management_keyboard(),
            )
    elif action == "cancel_add":
        context.user_data.pop("pending_admin", None)
        await query.edit_message_text(_admins_text(), reply_markup=admin_management_keyboard())
    elif action == "remove" and len(parts) == 3 and parts[2].isdigit():
        removed_id = int(parts[2])
        remove_bot_admin(removed_id)
        await query.edit_message_text(_admins_text(), reply_markup=admin_management_keyboard())
    elif action == "back":
        context.user_data.pop("admin_management_action", None)
        await query.edit_message_text(
            "🛠 Админская панель\n\nВыберите действие:",
            reply_markup=admin_panel_keyboard(True),
        )


async def handle_admin_management_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = require_effective_user(update).id
    if not is_owner(user_id) or context.user_data.get("admin_management_action") != "add":
        return
    message = require_message_target(update)
    text = (message.text or "").strip()
    if text.isdigit() and int(text) > 0:
        new_admin_id = int(text)
        display_name = str(new_admin_id)
        user_record = get_user_profile(new_admin_id)
    else:
        username = text.lstrip("@").strip()
        if not username.replace("_", "").isalnum() or len(username) < 5:
            await message.reply_text("⚠️ Отправьте корректный @username Telegram.")
            raise ApplicationHandlerStop
        user_record = get_user_by_username(username)
        new_admin_id = int(user_record[0]) if user_record else 0
        display_name = f"@{username}"

    if not user_record:
        await message.reply_text(
            "⚠️ Пользователь не найден. Попросите его открыть бота и нажать /start, "
            "затем повторите попытку."
        )
        raise ApplicationHandlerStop
    if new_admin_id == ADMIN_ID:
        await message.reply_text("ℹ️ Владелец уже имеет максимальные права.")
        context.user_data.pop("admin_management_action", None)
        raise ApplicationHandlerStop

    context.user_data["pending_admin"] = new_admin_id
    context.user_data.pop("admin_management_action", None)
    await message.reply_text(
        f"👤 Найден пользователь: {display_name}\n"
        f"🆔 ID: {new_admin_id}\n\nДобавить его как администратора?",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Добавить", callback_data=f"admin_admins:confirm_add:{new_admin_id}"),
                InlineKeyboardButton("❌ Отмена", callback_data="admin_admins:cancel_add"),
            ]
        ]),
    )
    raise ApplicationHandlerStop


async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(require_effective_user(update).id):
        return
    message = require_message_target(update)
    if not context.args or not context.args[0].isdigit():
        await message.reply_text("Использование: /ban USER_ID причина")
        return
    user_id = int(context.args[0])
    reason = " ".join(context.args[1:]) or "Заблокирован администратором"
    ban_user(user_id, ADMIN_ID, reason)
    await message.reply_text(f"✅ Пользователь {user_id} заблокирован.")


async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(require_effective_user(update).id):
        return
    message = require_message_target(update)
    if not context.args or not context.args[0].isdigit():
        await message.reply_text("Использование: /unban USER_ID")
        return
    user_id = int(context.args[0])
    result = unban_user(user_id)
    await message.reply_text(
        "✅ Пользователь разблокирован." if result else "ℹ️ Пользователь не найден в списке банов."
    )


async def banned_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(require_effective_user(update).id):
        return
    banned = get_banned_users()
    text = "🚫 Бан-лист пуст." if not banned else "🚫 Бан-лист:\n\n" + "\n".join(
        f"• {user_id} — {reason or 'без причины'}" for user_id, reason, _ in banned
    )
    await require_message_target(update).reply_text(text[:4000])


async def handle_admin_reply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None or query.message is None or not is_admin(require_effective_user(update).id):
        return

    await query.answer()
    try:
        user_id = int(query.data.split(":", 1)[1])
    except (AttributeError, ValueError, IndexError):
        await query.message.reply_text("❌ Некорректный получатель.")
        return

    context.user_data["admin_reply_to"] = user_id
    await query.message.reply_text(
        f"✍️ Напишите ответ пользователю {user_id}.\n"
        "Для отмены используйте /cancel_reply."
    )


async def handle_admin_ban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    actor_id = require_effective_user(update).id
    if query is None or query.message is None or not is_admin(actor_id) or not query.data:
        return
    try:
        target_id = int(query.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await query.message.reply_text("❌ Некорректный ID пользователя.")
        return

    if is_admin(target_id):
        await query.answer("Администраторов блокировать нельзя.", show_alert=True)
        return

    await query.answer()
    ban_user(target_id, actor_id, "Заблокирован через админ-панель")
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except BadRequest:
        pass
    await query.message.reply_text(f"🚫 Пользователь {target_id} заблокирован.")


async def handle_admin_unban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None or query.message is None or not is_admin(require_effective_user(update).id) or not query.data:
        return
    try:
        target_id = int(query.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await query.message.reply_text("❌ Некорректный ID пользователя.")
        return
    if unban_user(target_id):
        await query.answer("Пользователь разблокирован.", show_alert=True)
    else:
        await query.answer("Пользователь не найден в бан-листе.", show_alert=True)
    banned = get_banned_users()
    text = "🚫 Заблокированных пользователей нет." if not banned else "🚫 Заблокированные пользователи:\n\n" + "\n".join(
        f"• {blocked_id} — {reason or 'без причины'}" for blocked_id, reason, _ in banned
    )
    await query.edit_message_text(text[:4000], reply_markup=banned_users_keyboard(banned))


async def handle_admin_reply_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(require_effective_user(update).id):
        return

    user_id = context.user_data.get("admin_reply_to")
    message = require_message_target(update)
    if not user_id:
        return

    text = message.text
    if not text:
        return

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"📩 Ответ администратора:\n\n{text}",
        )
        await message.reply_text("✅ Ответ отправлен пользователю.")
    except Exception as error:
        await message.reply_text(f"❌ Не удалось отправить ответ: {error}")
    finally:
        context.user_data.pop("admin_reply_to", None)

    raise ApplicationHandlerStop


async def cancel_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(require_effective_user(update).id):
        return
    context.user_data.pop("admin_reply_to", None)
    await require_message_target(update).reply_text("✅ Ответ отменён.")


async def handle_premium_stub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None or query.message is None:
        return
    await query.answer("⭐ Premium будет добавлен позже.")
    await query.message.reply_text("⭐ Premium будет добавлен позже.")


async def handle_bonus_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    if query is None or query.message is None or user is None:
        return
    await query.answer()

    if has_active_bonus_request(user.id):
        await query.message.reply_text(
            "⏳ Ваш запрос уже отправлен.\n"
            "Пожалуйста, дождитесь решения администратора."
        )
        return

    request_id = create_bonus_download_request(
        user.id,
        user.username,
        user.first_name,
    )

    if not request_id:
        await query.message.reply_text(
            "⏳ Ваш запрос уже отправлен.\n"
            "Пожалуйста, дождитесь решения администратора."
        )
        return

    profile = get_user_profile(user.id) or (None, None, 0, None, 0, None, 0)
    first_name, username, is_premium, premium_until, downloads_today, registered_at, bonus_downloads_total = profile
    total_downloads = get_user_total_downloads(user.id)

    admin_text = (
        "📢 Новый запрос на дополнительные скачивания\n\n"
        f"👤 Имя пользователя: {first_name or '-'}\n"
        f"🔗 Username: @{username if username else '-'}\n"
        f"🆔 Telegram ID: {user.id}\n\n"
        f"📊 Сегодня использовано: {downloads_today}/{FREE_DAILY_LIMIT}\n"
        f"📈 Всего скачиваний: {total_downloads}\n"
        f"📅 Дата регистрации: {registered_at or '-'}\n"
        f"🎁 Сколько раз ранее получал дополнительные скачивания: {bonus_downloads_total}\n\n"
        f"🕒 Дата и время запроса: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ +5", callback_data=f"admin_bonus:approve:5:{request_id}"),
                InlineKeyboardButton("➕ +10", callback_data=f"admin_bonus:approve:10:{request_id}"),
                InlineKeyboardButton("➕ +20", callback_data=f"admin_bonus:approve:20:{request_id}"),
            ],
            [InlineKeyboardButton("❌ Отказать", callback_data=f"admin_bonus:decline:0:{request_id}")],
        ]
    )

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=admin_text,
        reply_markup=keyboard,
    )
    await query.message.reply_text(
        "✅ Ваш запрос отправлен администратору.\n"
        "Ожидайте решения."
    )


async def handle_admin_bonus_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None or query.message is None:
        return
    if not is_admin(require_effective_user(update).id):
        await query.answer("Доступ запрещён.", show_alert=True)
        return

    await query.answer()

    parts = query.data.split(":")
    if len(parts) != 4:
        return

    decision, amount, request_id = parts[1], parts[2], parts[3]
    request_id = int(request_id)
    amount = int(amount)
    actor_id = require_effective_user(update).id

    request = get_bonus_request(request_id)
    if not request:
        await query.edit_message_text("❌ Запрос уже неактивен.", reply_markup=None)
        return

    if decision == "approve":
        approved = approve_bonus_request(request_id, amount, actor_id)
        if approved:
            user_id = request[1]
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "🎉 Администратор одобрил ваш запрос.\n\n"
                    f"Вам начислено ещё {amount} дополнительных скачиваний."
                ),
            )
            await query.edit_message_text(
                f"✅ Пользователю выдано +{amount}",
                reply_markup=None,
            )
        else:
            await query.edit_message_text("❌ Не удалось обработать запрос.", reply_markup=None)
      
    else:
        decline_bonus_request(request_id, actor_id)
        user_id = request[1]
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "❌ К сожалению, запрос отклонён.\n"
                "Попробуйте снова завтра или приобретите Premium."
            ),
        )
        await query.edit_message_text("❌ Запрос отклонён.", reply_markup=None)
