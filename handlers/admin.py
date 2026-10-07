from datetime import datetime
import asyncio
from html import escape
import re
import sqlite3

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, TelegramError
from telegram.ext import ApplicationHandlerStop, ContextTypes
from utils.message_utils import require_effective_user, require_message_target

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
    get_admin_dashboard_stats,
    ban_user,
    get_banned_users,
    unban_user,
    add_bot_admin,
    remove_bot_admin,
    get_bot_admins,
    get_download_stats_by_service,
    get_recent_users,
    get_recent_security_events,
    get_registered_user_ids,
    get_user_by_username,
    get_admin_downloads_page,
    find_admin_download_users,
    get_admin_user_download_summary,
    get_admin_audit_page,
    preview_premium_expiry,
    update_user_premium,
    get_reminder_settings,
    update_bot_setting,
)
from utils.i18n import translate
from utils.admin_roles import is_admin, is_owner
from utils.chat_cleanup import clear_ui_messages, delete_button_message, remember_ui_message
from handlers.health import health_report_text


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
        [InlineKeyboardButton("📥 Журнал скачиваний", callback_data="admin_downloads:open")],
        [InlineKeyboardButton("🛡 Безопасность", callback_data="admin_panel:security")],
        [InlineKeyboardButton("🩺 Здоровье", callback_data="admin_panel:health")],
        [InlineKeyboardButton("🔔 Напоминания", callback_data="admin_panel:reminders")],
        [InlineKeyboardButton("🔄 Обновить", callback_data="admin_panel:refresh")],
    ]
    if owner:
        rows.append([InlineKeyboardButton("👥 Администраторы", callback_data="admin_panel:admins")])
        rows.append([InlineKeyboardButton("📣 Уведомить о новинках", callback_data="admin_panel:news")])
    rows.append([InlineKeyboardButton("⬅️ В главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(rows)


def admin_submenu_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⬅️ В админ-панель", callback_data="admin_panel:home")
    ]])


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = require_effective_user(update).id
    if not is_admin(user_id):
        return
    message = require_message_target(update)
    if update.callback_query is not None:
        await query_edit_admin_panel(update, user_id)
        return
    await clear_ui_messages(context, message.chat_id)
    sent = await message.reply_text(
        "🛠 Админская панель\n\nВыберите действие:",
        reply_markup=admin_panel_keyboard(is_owner(user_id)),
    )
    remember_ui_message(context, sent)
    if message.text and message.text.startswith("/"):
        await delete_button_message(message)


async def query_edit_admin_panel(update: Update, user_id: int):
    query = update.callback_query
    await query.edit_message_text(
        "🛠 Админская панель\n\nВыберите действие:",
        reply_markup=admin_panel_keyboard(is_owner(user_id)),
    )


async def handle_admin_entry_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = require_effective_user(update).id
    if query is None or not is_admin(user_id):
        return
    await query.answer()
    await clear_ui_messages(
        context,
        query.message.chat_id,
        keep_ids=(query.message.message_id,),
    )
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

    if action == "home":
        await query.edit_message_text(
            "🛠 Админская панель\n\nВыберите действие:",
            reply_markup=admin_panel_keyboard(is_owner(user_id)),
        )
    elif action in {"status", "refresh"}:
        stats = get_admin_dashboard_stats()
        text = (
            "🛠 Dashboard\n\n"
            f"👥 Всего пользователей: {stats['users']}\n"
            f"🟢 Активных за 24 часа: {stats['active_24h']}\n"
            f"🆕 Новых сегодня: {stats['new_today']}\n"
            f"📅 Новых за 7 дней: {stats['new_7d']}\n\n"
            f"📥 Скачиваний сегодня: {stats['downloads_today']}\n"
            f"📊 Скачиваний за 7 дней: {stats['downloads_7d']}\n"
            f"📈 Скачиваний за 30 дней: {stats['downloads_30d']}\n\n"
            "🔥 Популярные сервисы за 30 дней:\n"
            + ("\n".join(f"• {name}: {count}" for name, count in stats["services"]) or "• Данных пока нет")
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
                f"• {blocked_id} — {reason or 'без причины'}"
                for blocked_id, reason, _ in banned
            )
        await query.edit_message_text(text[:4000], reply_markup=banned_users_keyboard(banned))
    elif action == "services":
        rows = get_download_stats_by_service()
        text = "📈 Скачивания по сервисам\n\n"
        text += "\n".join(f"• {media_type}: {count}" for media_type, count in rows) or "Данных пока нет."
        await query.edit_message_text(text[:4000], reply_markup=admin_submenu_keyboard())
    elif action == "users":
        await _show_admin_users(query)
    elif action == "security":
        await _show_admin_audit(query)
    elif action == "health":
        text = await health_report_text()
        await query.edit_message_text(text[:4000], reply_markup=admin_submenu_keyboard())
    elif action == "reminders" and is_owner(user_id):
        await query.edit_message_text(_reminders_text(), reply_markup=reminders_keyboard())
    elif action == "admins" and is_owner(user_id):
        await query.edit_message_text(_admins_text(), reply_markup=admin_management_keyboard())
    elif action == "news" and is_owner(user_id):
        count = len(get_registered_user_ids())
        await query.edit_message_text(
            f"📣 Уведомление о новых возможностях будет отправлено пользователям: {count}.\n\n"
            "Отправить сейчас?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Отправить", callback_data="admin_news:send")],
                [InlineKeyboardButton("⬅️ Отмена", callback_data="admin_panel:status")],
            ]),
        )


DOWNLOAD_SERVICE_FILTERS = {
    "all": "Все сервисы",
    "instagram": "Instagram",
    "youtube": "YouTube",
    "tiktok": "TikTok",
    "facebook": "Facebook",
    "pinterest": "Pinterest",
}


def _admin_audit_keyboard(page: int, user_id: int | None, total: int):
    rows = [[InlineKeyboardButton(
        "🔎 Фильтр по пользователю" if user_id is None else "🔎 Изменить пользователя",
        callback_data="admin_audit:search",
    )]]
    if user_id is not None:
        rows.append([InlineKeyboardButton("✖️ Сбросить фильтр", callback_data="admin_audit:open")])
    last_page = max(0, (total - 1) // 10)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Новее", callback_data=f"admin_audit:page:{page - 1}:{user_id or 0}"))
    if page < last_page:
        nav.append(InlineKeyboardButton("Старее ➡️", callback_data=f"admin_audit:page:{page + 1}:{user_id or 0}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("⬅️ В админ-панель", callback_data="admin_panel:home")])
    return InlineKeyboardMarkup(rows)


async def _show_admin_audit(query, page: int = 0, user_id: int | None = None):
    records, total = get_admin_audit_page(page, 10, user_id)
    last_page = max(0, (total - 1) // 10)
    page = min(max(0, page), last_page)
    if page >= 0 and not records and total and page:
        page = last_page
        records, total = get_admin_audit_page(page, 10, user_id)
    lines = [
        "🛡 <b>Действия администраторов</b>",
        "Здесь сохраняются изменения Premium, блокировки и назначения администраторов.",
        f"Фильтр: пользователь <code>{user_id}</code>" if user_id else "Фильтр: все пользователи",
        f"Всего записей: {total} · Страница {page + 1}/{last_page + 1}\n",
    ]
    labels = {
        "PREMIUM_GRANTED": "⭐ Premium выдан/продлён",
        "PREMIUM_REVOKED": "⭐ Premium отключён",
        "USER_BANNED": "🚫 Пользователь заблокирован",
        "USER_UNBANNED": "✅ Пользователь разблокирован",
        "ADMIN_ADDED": "👮 Администратор добавлен",
        "ADMIN_REMOVED": "👮 Администратор снят",
    }
    for target, username, first_name, action, details, actor, created in records:
        identity = f"{escape(first_name or username or 'Без имени')} · <code>{target}</code>"
        if username:
            identity += f" · @{escape(username)}"
        actor_profile = get_user_profile(actor) if actor else None
        actor_name = (actor_profile[0] or actor_profile[1]) if actor_profile else None
        actor_label = escape(actor_name or str(actor or "не указан"))
        if actor:
            actor_label = f'<a href="tg://user?id={actor}">{actor_label}</a>'
        detail_text = ""
        if details:
            raw_details = str(details)
            raw_details = re.sub(rf"^Администратор\s+{actor}\s+", "", raw_details) if actor else raw_details
            premium_info = re.search(r"Premium на (\d+) дней; до (.+)$", raw_details)
            if premium_info:
                detail_text = f"Срок: {premium_info.group(1)} дн. · до {premium_info.group(2)}"
            elif action == "USER_BANNED" and raw_details:
                detail_text = f"Причина: {raw_details}"
        lines.append(
            f"📅 <b>{escape(str(created or ''))}</b>\n"
            f"{labels.get(action, 'Действие')}\n"
            f"👤 Пользователь: {identity}\n🛠 Кто выполнил: {actor_label}"
        )
        if detail_text:
            lines.append(escape(detail_text[:180]))
        lines.append("")
    if not records:
        lines.append("Записей пока нет.")
    await query.edit_message_text(
        "\n".join(lines)[:4000], parse_mode="HTML",
        reply_markup=_admin_audit_keyboard(page, user_id, total),
    )


async def handle_admin_audit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    actor_id = require_effective_user(update).id
    if query is None or query.message is None or not query.data or not is_admin(actor_id):
        return
    await query.answer()
    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else "open"
    if action == "search":
        context.user_data["admin_audit_search"] = True
        await query.edit_message_text(
            "🔎 Отправьте Telegram ID или @username целевого пользователя.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✖️ Отмена", callback_data="admin_audit:open")]]),
        )
        return
    context.user_data.pop("admin_audit_search", None)
    page, user_id = 0, None
    if action == "page":
        try:
            page = max(0, int(parts[2]))
            user_id = int(parts[3]) or None
        except (IndexError, ValueError):
            pass
    elif action == "user" and len(parts) > 2:
        try:
            user_id = int(parts[2])
        except ValueError:
            user_id = None
    await _show_admin_audit(query, page, user_id)


async def _show_admin_users(query):
    rows = get_recent_users(10)
    lines = ["👥 <b>Пользователи</b>", "Выберите пользователя для просмотра карточки и управления Premium:"]
    buttons = []
    for telegram_id, username, first_name, is_premium, downloads_today, _ in rows:
        name = (first_name or username or "Без имени")[:22]
        status = "⭐" if is_premium else "👤"
        buttons.append([InlineKeyboardButton(
            f"{status} {name} · {telegram_id}", callback_data=f"admin_users:user:{telegram_id}"
        )])
    if not rows:
        lines.append("\nПользователей пока нет.")
    buttons.extend([
        [InlineKeyboardButton("🔎 Найти пользователя", callback_data="admin_users:search")],
        [InlineKeyboardButton("⬅️ В админ-панель", callback_data="admin_panel:home")],
    ])
    await query.edit_message_text("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def _show_admin_user_card(query, user_id: int, notice: str | None = None):
    summary = get_admin_user_download_summary(user_id)
    if not summary:
        await query.edit_message_text(
            "Пользователь не найден в базе.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ К пользователям", callback_data="admin_users:open")]]),
        )
        return
    user, total_downloads, last_download = summary
    _, username, first_name, premium, premium_until, registered = user
    name = escape(first_name or username or str(user_id))
    status = f"⭐ Premium до {escape(str(premium_until or 'без срока'))}" if premium else "Обычный аккаунт"
    text = (
        f"👤 <b>Карточка пользователя</b>\n\n{name}\n"
        f"ID: <code>{user_id}</code>\nUsername: @{escape(username or '-')}\n"
        f"Статус: {status}\nУспешных скачиваний: {total_downloads}\n"
        f"Последнее скачивание: {escape(str(last_download or 'нет'))}\n"
        f"Регистрация: {escape(str(registered or 'неизвестно'))}"
    )
    if notice:
        text += f"\n\n✅ {escape(notice)}"
    await query.edit_message_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⭐ Управление Premium", callback_data=f"admin_users:premium:{user_id}")],
            [InlineKeyboardButton("📥 Скачивания пользователя", callback_data=f"admin_downloads:user:{user_id}")],
            [InlineKeyboardButton("⬅️ К пользователям", callback_data="admin_users:open")],
        ]),
    )


async def handle_admin_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    actor_id = require_effective_user(update).id
    if query is None or query.message is None or not query.data or not is_admin(actor_id):
        return
    await query.answer()
    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else "open"
    if action == "search":
        context.user_data["admin_users_search"] = True
        await query.edit_message_text(
            "🔎 Отправьте Telegram ID или @username пользователя.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✖️ Отмена", callback_data="admin_users:open")]]),
        )
    elif action == "user" and len(parts) > 2 and parts[2].isdigit():
        context.user_data.pop("admin_users_search", None)
        await _show_admin_user_card(query, int(parts[2]))
    elif action == "premium" and len(parts) > 2 and parts[2].isdigit():
        await _show_premium_management(query, int(parts[2]), prefix="admin_users")
    elif action == "premium_confirm" and len(parts) == 4 and parts[2].isdigit():
        selected_user, choice = int(parts[2]), parts[3]
        if choice == "off":
            confirmation = "Отключить Premium этому пользователю?"
        elif choice.isdigit() and int(choice) in {7, 30, 90}:
            expiry = preview_premium_expiry(selected_user, int(choice))
            if expiry is None:
                await _show_premium_management(query, selected_user, prefix="admin_users")
                return
            confirmation = f"Выдать/продлить Premium на {choice} дней?\nНовый срок: {expiry}"
        else:
            return
        await query.edit_message_text(
            f"⚠️ <b>Подтвердите действие</b>\n\n{confirmation}", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Подтвердить", callback_data=f"admin_users:premium_apply:{selected_user}:{choice}")],
                [InlineKeyboardButton("↩️ Отмена", callback_data=f"admin_users:premium:{selected_user}")],
            ]),
        )
    elif action == "premium_apply" and len(parts) == 4 and parts[2].isdigit():
        selected_user, choice = int(parts[2]), parts[3]
        days = None if choice == "off" else (int(choice) if choice.isdigit() else -1)
        result = update_user_premium(selected_user, days, actor_id)
        if not result:
            await query.edit_message_text("❌ Не удалось изменить Premium: пользователь не найден.")
            return
        if result.get("error") == "permanent":
            await _show_premium_management(query, selected_user, prefix="admin_users")
            return
        try:
            message = (f"🎉 Вам выдан или продлён Premium. Подписка действует до {result['premium_until']}."
                       if result["is_premium"] else "ℹ️ Администратор отключил Premium-доступ. Бесплатный лимит скачиваний снова действует.")
            await context.bot.send_message(chat_id=selected_user, text=message)
            notice = "Пользователь уведомлён."
        except TelegramError:
            notice = "Не удалось отправить уведомление пользователю."
        await _show_admin_user_card(query, selected_user, f"Изменения сохранены. {notice}")
    else:
        context.user_data.pop("admin_users_search", None)
        await _show_admin_users(query)


def _admin_downloads_keyboard(page: int, service: str, user_id: int | None, total: int):
    rows = []
    service_buttons = []
    for key, label in DOWNLOAD_SERVICE_FILTERS.items():
        caption = f"✅ {label}" if key == service else label
        service_buttons.append(InlineKeyboardButton(
            caption,
            callback_data=f"admin_downloads:filter:{key}:{user_id or 0}",
        ))
        if len(service_buttons) == 2:
            rows.append(service_buttons)
            service_buttons = []
    if service_buttons:
        rows.append(service_buttons)
    rows.append([InlineKeyboardButton("🔎 Найти пользователя", callback_data="admin_downloads:search")])

    last_page = max(0, (total - 1) // 10)
    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton(
            "⬅️ Новее", callback_data=f"admin_downloads:page:{page - 1}:{service}:{user_id or 0}"
        ))
    if page < last_page:
        navigation.append(InlineKeyboardButton(
            "Старее ➡️", callback_data=f"admin_downloads:page:{page + 1}:{service}:{user_id or 0}"
        ))
    if navigation:
        rows.append(navigation)
    if user_id is not None:
        rows.append([InlineKeyboardButton("📋 Все скачивания", callback_data="admin_downloads:open")])
    rows.append([InlineKeyboardButton("⬅️ В админ-панель", callback_data="admin_panel:home")])
    return InlineKeyboardMarkup(rows)


async def _show_admin_downloads(
    query, page: int = 0, service: str = "all", user_id: int | None = None, notice: str | None = None
):
    service = service if service in DOWNLOAD_SERVICE_FILTERS else "all"
    summary_text = ""
    if user_id is not None:
        summary = get_admin_user_download_summary(user_id)
        if summary:
            user, total_user_downloads, last_download = summary
            _, username, first_name, premium, premium_until, registered = user
            display = escape((first_name or username or "Без имени")[:80])
            summary_text = (
                f"\n\n👤 <b>{display}</b> · ID <code>{user_id}</code>\n"
                f"Username: @{escape(username or '-')} · {'⭐ Premium' if premium else 'Обычный'}\n"
                f"Успешных загрузок: {total_user_downloads}\n"
                f"Последняя: {escape(str(last_download or 'нет'))}"
            )
            if premium:
                summary_text += f"\nPremium до: {escape(str(premium_until or 'Без срока'))}"
            if registered:
                summary_text += f"\nРегистрация: {escape(str(registered))}"
        else:
            summary_text = f"\n\n👤 ID <code>{user_id}</code> · карточка пользователя не найдена"

    service_filter = None if service == "all" else service
    requested_page = page
    records, total = get_admin_downloads_page(page, 10, service_filter, user_id)
    last_page = max(0, (total - 1) // 10)
    page = min(max(0, page), last_page)
    if page != requested_page:
        records, total = get_admin_downloads_page(page, 10, service_filter, user_id)

    title = "📥 <b>Журнал успешных скачиваний</b>"
    title += f"\nФильтр: {DOWNLOAD_SERVICE_FILTERS[service]}"
    if user_id is not None:
        title += " · выбран пользователь"
    title += f"\nЗаписей: {total} · Страница {page + 1}/{last_page + 1}"
    lines = [title + summary_text, ""]
    if notice:
        lines.extend([escape(notice), ""])
    if records:
        for index, (record_user_id, username, first_name, url, media_type, created_at) in enumerate(records, start=1):
            label = escape((first_name or username or "Неизвестный пользователь")[:80])
            username_text = f"@{escape(username[:32])}" if username else "без username"
            lines.append(
                f"<b>{page * 10 + index}.</b> {escape(str(created_at or ''))}\n"
                f"👤 {label} ({username_text}, ID <code>{record_user_id or '-'}"
                f"</code>)\n📦 {escape(str(media_type or 'Тип не указан')[:100])}"
            )
            safe_url = str(url or "")
            if safe_url.startswith(("https://", "http://")):
                lines.append(f'🔗 <a href="{escape(safe_url, quote=True)}">Открыть публикацию</a>')
            lines.append("")
    else:
        lines.append("По этому фильтру записей пока нет.")

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=_admin_downloads_keyboard(page, service, user_id, total),
        disable_web_page_preview=True,
    )


async def _show_premium_management(query, user_id: int, prefix: str = "admin_users"):
    summary = get_admin_user_download_summary(user_id)
    if not summary:
        await query.edit_message_text(
            "Пользователь не найден.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                "⬅️ Назад", callback_data="admin_users:user:" + str(user_id)
            )]]),
        )
        return

    user, _, _ = summary
    _, username, first_name, is_premium, premium_until, _ = user
    display_name = escape(first_name or username or str(user_id))
    if is_premium:
        current_status = f"Активен до: {escape(str(premium_until or 'Без срока'))}"
    else:
        current_status = "Сейчас не активен"

    rows = []
    if not (is_premium and not premium_until):
        rows.extend([
            [InlineKeyboardButton("➕ 7 дней", callback_data=f"{prefix}:premium_confirm:{user_id}:7"),
             InlineKeyboardButton("➕ 30 дней", callback_data=f"{prefix}:premium_confirm:{user_id}:30")],
            [InlineKeyboardButton("➕ 90 дней", callback_data=f"{prefix}:premium_confirm:{user_id}:90")],
        ])
    if is_premium:
        rows.append([InlineKeyboardButton(
            "⛔ Отключить Premium", callback_data=f"{prefix}:premium_confirm:{user_id}:off"
        )])
    rows.append([InlineKeyboardButton(
        "⬅️ К карточке пользователя", callback_data=f"admin_users:user:{user_id}"
    )])
    await query.edit_message_text(
        f"⭐ <b>Управление Premium</b>\n\n"
        f"👤 {display_name} · ID <code>{user_id}</code>\n"
        f"Username: @{escape(username or '-')}\n"
        f"Статус: {current_status}\n\n"
        "Выберите срок. Перед изменением появится подтверждение.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def handle_admin_downloads_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = require_effective_user(update).id
    if query is None or query.message is None or not query.data or not is_admin(user_id):
        return
    await query.answer()
    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else "open"
    if action in {"open", "filter", "page", "user"}:
        context.user_data.pop("admin_download_search", None)
        page, service, selected_user = 0, "all", None
        if action == "filter" and len(parts) > 2:
            service = parts[2]
            if len(parts) > 3 and parts[3].isdigit() and int(parts[3]) > 0:
                selected_user = int(parts[3])
        elif action == "page" and len(parts) > 2:
            try:
                page = max(0, int(parts[2]))
            except ValueError:
                pass
            if len(parts) > 3 and parts[3] in DOWNLOAD_SERVICE_FILTERS:
                service = parts[3]
            if len(parts) > 4 and parts[4].isdigit() and int(parts[4]) > 0:
                selected_user = int(parts[4])
        elif action == "user" and len(parts) > 2:
            try:
                selected_user = int(parts[2])
            except ValueError:
                pass
        await _show_admin_downloads(query, page, service, selected_user)
    elif action == "search":
        context.user_data["admin_download_search"] = True
        await query.edit_message_text(
            "🔎 Отправьте Telegram ID или @username пользователя.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                "✖️ Отмена", callback_data="admin_downloads:open"
            )]]),
        )
    elif action == "results" and len(parts) > 2:
        context.user_data.pop("admin_download_search", None)
        try:
            selected_user = int(parts[2])
        except ValueError:
            selected_user = None
        await _show_admin_downloads(query, user_id=selected_user)
    elif action == "premium" and len(parts) > 2:
        try:
            selected_user = int(parts[2])
        except ValueError:
            return
        await _show_premium_management(query, selected_user)
    elif action == "premium_confirm" and len(parts) == 4:
        try:
            selected_user = int(parts[2])
        except ValueError:
            return
        choice = parts[3]
        if choice == "off":
            confirmation = "Отключить Premium этому пользователю?"
        elif choice.isdigit() and int(choice) in {7, 30, 90}:
            expiry = preview_premium_expiry(selected_user, int(choice))
            if expiry is None:
                await _show_premium_management(query, selected_user)
                return
            confirmation = f"Выдать/продлить Premium на {choice} дней?\nНовый срок: {expiry}"
        else:
            return
        await query.edit_message_text(
            f"⚠️ <b>Подтвердите действие</b>\n\n{confirmation}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Подтвердить", callback_data=f"admin_downloads:premium_apply:{selected_user}:{choice}")],
                [InlineKeyboardButton("↩️ Отмена", callback_data=f"admin_downloads:premium:{selected_user}")],
            ]),
        )
    elif action == "premium_apply" and len(parts) == 4:
        try:
            selected_user = int(parts[2])
        except ValueError:
            return
        choice = parts[3]
        days = None if choice == "off" else (int(choice) if choice.isdigit() else -1)
        result = update_user_premium(selected_user, days, user_id)
        if not result:
            await query.edit_message_text("❌ Не удалось изменить Premium: пользователь не найден.")
            return
        if result.get("error") == "permanent":
            await _show_premium_management(query, selected_user)
            return

        try:
            if result["is_premium"]:
                await context.bot.send_message(
                    chat_id=selected_user,
                    text=f"🎉 Вам выдан или продлён Premium. Подписка действует до {result['premium_until']}.",
                )
            else:
                await context.bot.send_message(
                    chat_id=selected_user,
                    text="ℹ️ Администратор отключил Premium-доступ. Бесплатный лимит скачиваний снова действует.",
                )
            notification_status = "Пользователь уведомлён."
        except TelegramError:
            notification_status = "Не удалось отправить уведомление (возможно, бот заблокирован)."
        await _show_admin_downloads(
            query,
            user_id=selected_user,
            notice=f"✅ Изменения Premium сохранены. {notification_status}",
        )

async def handle_admin_news_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = require_effective_user(update).id
    if query is None or query.message is None or not is_owner(user_id):
        return
    await query.answer()
    if query.data != "admin_news:send":
        return

    await query.edit_message_reply_markup(reply_markup=None)

    user_ids = get_registered_user_ids()
    delivered = 0
    failed = 0
    for recipient_id in user_ids:
        language = get_user_settings(recipient_id)["language"]
        try:
            await context.bot.send_message(
                chat_id=recipient_id,
                text=translate(language, "news_text"),
            )
            delivered += 1
        except TelegramError:
            failed += 1
        await asyncio.sleep(0.05)

    await query.edit_message_text(
        "📣 Рассылка завершена.\n\n"
        f"✅ Доставлено: {delivered}\n"
        f"⚠️ Не доставлено: {failed}",
        reply_markup=admin_panel_keyboard(is_owner(user_id)),
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
        await query.edit_message_text(
            "➕ Отправьте @username пользователя, которого нужно сделать администратором.\n"
            "Пользователь должен сначала запустить бота.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Назад", callback_data="admin_admins:cancel_add")
            ]]),
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
        context.user_data.pop("admin_management_action", None)
        await query.edit_message_text(_admins_text(), reply_markup=admin_management_keyboard())
    elif action == "remove" and len(parts) == 3 and parts[2].isdigit():
        removed_id = int(parts[2])
        remove_bot_admin(removed_id, user_id)
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
    ban_user(user_id, require_effective_user(update).id, reason)
    await message.reply_text(f"✅ Пользователь {user_id} заблокирован.")


async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(require_effective_user(update).id):
        return
    message = require_message_target(update)
    if not context.args or not context.args[0].isdigit():
        await message.reply_text("Использование: /unban USER_ID")
        return
    user_id = int(context.args[0])
    result = unban_user(user_id, require_effective_user(update).id)
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
    if unban_user(target_id, actor_id):
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

    message = require_message_target(update)
    if context.user_data.pop("admin_users_search", False):
        query_text = (message.text or "").strip()
        selected_user = int(query_text) if query_text.isdigit() else None
        if selected_user is None:
            record = get_user_by_username(query_text)
            if record:
                selected_user = int(record[0])
        if selected_user is None or not get_admin_user_download_summary(selected_user):
            await message.reply_text("🔎 Пользователь не найден. Он должен сначала запустить бота.")
        else:
            await message.reply_text(
                f"👤 Пользователь найден: {selected_user}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                    "Открыть карточку", callback_data=f"admin_users:user:{selected_user}"
                )]]),
            )
        raise ApplicationHandlerStop

    if context.user_data.pop("admin_audit_search", False):
        query_text = (message.text or "").strip()
        selected_user = None
        if query_text.isdigit():
            selected_user = int(query_text)
        else:
            user = get_user_by_username(query_text)
            if user:
                selected_user = int(user[0])
        if selected_user is None:
            await message.reply_text("🔎 Пользователь не найден. Проверьте ID или username и попробуйте снова.")
        else:
            records, _ = get_admin_audit_page(0, 1, selected_user)
            if not records:
                await message.reply_text(f"Для пользователя {selected_user} действий в журнале пока нет.")
            else:
                await message.reply_text(
                    f"🔎 Журнал отфильтрован по пользователю {selected_user}.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                        "📋 Открыть журнал", callback_data=f"admin_audit:user:{selected_user}"
                    )]]),
                )
        raise ApplicationHandlerStop

    if context.user_data.pop("admin_download_search", False):
        matches = find_admin_download_users(message.text or "")
        if not matches:
            await message.reply_text("🔎 Пользователь не найден. Проверьте ID или username и попробуйте снова.")
        else:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    f"{(first_name or username or 'Пользователь')[:20]} · @{(username or '—')[:20]} · {telegram_id}",
                    callback_data=f"admin_downloads:results:{telegram_id}",
                )]
                for telegram_id, username, first_name in matches
            ] + [[InlineKeyboardButton("⬅️ В журнал", callback_data="admin_downloads:open")]])
            await message.reply_text(
                f"🔎 Найдено пользователей: {len(matches)}. Выберите нужного:",
                reply_markup=keyboard,
            )
        raise ApplicationHandlerStop

    user_id = context.user_data.get("admin_reply_to")
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
    first_name, username, is_premium, premium_until, downloads_today, registered_at, bonus_downloads_total = profile[:7]
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
