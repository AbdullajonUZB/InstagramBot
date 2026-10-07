import logging
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

DB_NAME = str(Path(__file__).resolve().parent / "history.db")

FREE_DAILY_LIMIT = 20


@contextmanager
def connect():
    Path(__file__).resolve().parent.mkdir(exist_ok=True)

    logger.debug("База: %s", Path(DB_NAME).resolve())

    conn = sqlite3.connect(DB_NAME, timeout=10)
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()
    finally:
        conn.close()


def _ensure_column(conn, table_name, column_name, definition):
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    existing_columns = {row[1] for row in cursor.fetchall()}
    if column_name not in existing_columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _premium_expiry(value):
    if not value:
        return None
    try:
        expiry = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if expiry.tzinfo is not None:
        expiry = expiry.astimezone().replace(tzinfo=None)
    return expiry


def _premium_is_active(conn, telegram_id: int, is_premium: int, premium_until: str | None) -> bool:
    if not is_premium:
        return False
    if not premium_until:
        return True  # Legacy no-expiry Premium remains active until revoked.
    expiry = _premium_expiry(premium_until)
    if expiry is None or expiry > datetime.now():
        return True
    conn.execute(
        "UPDATE users SET is_premium = 0, premium_until = NULL WHERE telegram_id = ?",
        (telegram_id,),
    )
    return False


def create_database():
    with connect() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                file_type TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users(
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                is_premium INTEGER NOT NULL DEFAULT 0,
                premium_until TEXT,
                downloads_today INTEGER NOT NULL DEFAULT 0,
                last_download_date TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS security_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                username TEXT,
                first_name TEXT,
                action TEXT,
                details TEXT,
                actor_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_settings(
                user_id INTEGER PRIMARY KEY,
                send_format TEXT NOT NULL DEFAULT 'video',
                history_enabled INTEGER NOT NULL DEFAULT 1,
                language TEXT NOT NULL DEFAULT 'ru'
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS downloads(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                username TEXT,
                first_name TEXT,
                url TEXT,
                media_type TEXT,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS bonus_requests(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT,
                request_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                bonus_downloads INTEGER NOT NULL DEFAULT 0,
                approved_by INTEGER,
                approved_at TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS banned_users(
                telegram_id INTEGER PRIMARY KEY,
                reason TEXT,
                banned_by INTEGER,
                banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback(
                user_id INTEGER PRIMARY KEY,
                rating INTEGER NOT NULL,
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_admins(
                telegram_id INTEGER PRIMARY KEY,
                role TEXT NOT NULL DEFAULT 'admin',
                added_by INTEGER NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_settings(
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS media_cache(
                cache_key TEXT PRIMARY KEY,
                media_type TEXT NOT NULL,
                file_id TEXT NOT NULL,
                caption_key TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS inline_trial_uses(
                query_id TEXT PRIMARY KEY,
                telegram_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.executemany(
            "INSERT OR IGNORE INTO bot_settings(setting_key, setting_value) VALUES (?, ?)",
            [("reminders_enabled", "1"), ("reminder_after_days", "7")],
        )

        _ensure_column(conn, "users", "registered_at", "TEXT")
        _ensure_column(conn, "users", "bonus_downloads_total", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "users", "last_seen_at", "TEXT")
        _ensure_column(conn, "users", "reminders_enabled", "INTEGER NOT NULL DEFAULT 1")
        _ensure_column(conn, "users", "last_reminder_at", "TEXT")
        _ensure_column(conn, "users", "language_code", "TEXT")
        _ensure_column(conn, "users", "bonus_downloads_remaining", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "users", "referral_eligible", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "users", "hidden_from_admin", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "security_log", "actor_id", "INTEGER")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS referrals(
                invited_user_id INTEGER PRIMARY KEY,
                referrer_user_id INTEGER NOT NULL,
                qualified INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                qualified_at TIMESTAMP
            )
            """
        )
        conn.execute("UPDATE users SET last_seen_at = COALESCE(last_seen_at, registered_at) WHERE last_seen_at IS NULL")
        # Backfill legacy successful downloads that were previously stored
        # only in the user history table.
        conn.execute(
            """
            INSERT INTO downloads(
                telegram_id, username, first_name, url, media_type, status, created_at
            )
            SELECT h.user_id, u.username, u.first_name, h.url, h.file_type,
                   'success', h.created_at
            FROM history h
            LEFT JOIN users u ON u.telegram_id = h.user_id
            WHERE NOT EXISTS (
                SELECT 1 FROM downloads d
                WHERE d.telegram_id = h.user_id
                  AND d.url = h.url
                  AND d.media_type = h.file_type
            )
            """
        )


def add_download(
    telegram_id,
    username,
    first_name,
    url,
    media_type,
    status,
):
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO downloads(
                telegram_id,
                username,
                first_name,
                url,
                media_type,
                status
            )
            VALUES(?,?,?,?,?,?)
            """,
            (
                telegram_id,
                username,
                first_name,
                url,
                media_type,
                status,
            ),
        )


def add_security_log(
    telegram_id,
    username,
    first_name,
    action,
    details,
    actor_id=None,
):
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO security_log(
                telegram_id,
                username,
                first_name,
                action,
                details,
                actor_id
            )
            VALUES(?,?,?,?,?,?)
            """,
            (
                telegram_id,
                username,
                first_name,
                action,
                details,
                actor_id,
            ),
        )


def get_history(user_id, limit=20):
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT file_type, url, created_at
            FROM history
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        rows = cursor.fetchall()

    return rows


def get_history_item(user_id, item_number: int):
    """Return one history item by its displayed 1-based number."""
    item_number = int(item_number)
    if item_number < 1:
        return None
    rows = get_history(user_id, limit=item_number)
    return rows[item_number - 1] if len(rows) >= item_number else None


def get_cached_media(cache_key: str):
    with connect() as conn:
        row = conn.execute(
            "SELECT media_type, file_id, caption_key FROM media_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE media_cache SET last_used_at = CURRENT_TIMESTAMP WHERE cache_key = ?",
                (cache_key,),
            )
    return row


def save_cached_media(cache_key: str, media_type: str, file_id: str, caption_key: str):
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO media_cache(cache_key, media_type, file_id, caption_key)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                media_type = excluded.media_type,
                file_id = excluded.file_id,
                caption_key = excluded.caption_key,
                last_used_at = CURRENT_TIMESTAMP
            """,
            (cache_key, media_type, file_id, caption_key),
        )


def consume_inline_trial(telegram_id: int, query_id: str, limit: int) -> tuple[bool, int]:
    """Reserve one inline preview for a unique query; return (allowed, used)."""
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT 1 FROM inline_trial_uses WHERE query_id = ? AND telegram_id = ?",
            (query_id, telegram_id),
        ).fetchone()
        if existing:
            used = conn.execute(
                "SELECT COUNT(*) FROM inline_trial_uses WHERE telegram_id = ?",
                (telegram_id,),
            ).fetchone()[0]
            return True, used

        used = conn.execute(
            "SELECT COUNT(*) FROM inline_trial_uses WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()[0]
        if used >= limit:
            return False, used

        conn.execute(
            "INSERT INTO inline_trial_uses(query_id, telegram_id) VALUES (?, ?)",
            (query_id, telegram_id),
        )
        return True, used + 1


def resolve_language(language, telegram_language_code=None):
    """Return a supported UI language, using Telegram language when set to auto."""
    if language != "auto":
        return language if language in {"ru", "uz", "en"} else "ru"

    code = (telegram_language_code or "").lower().replace("_", "-")
    if code.startswith("uz"):
        return "uz"
    if code.startswith("en"):
        return "en"
    return "ru"


def get_user_settings(user_id):
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO user_settings (user_id)
            VALUES (?)
            """,
            (user_id,),
        )
        cursor.execute(
            """
            SELECT s.send_format, s.history_enabled, s.language, u.language_code
            FROM user_settings s
            LEFT JOIN users u ON u.telegram_id = s.user_id
            WHERE s.user_id = ?
            """,
            (user_id,),
        )
        row = cursor.fetchone()

    send_format, history_enabled, language, language_code = row
    language_preference = language
    language = resolve_language(language, language_code)

    return {
        "send_format": send_format,
        "history_enabled": bool(history_enabled),
        "language": language,
        "language_preference": language_preference,
    }


def update_user_settings(user_id, **settings):
    allowed = {"send_format", "history_enabled", "language"}
    values = {key: value for key, value in settings.items() if key in allowed}

    if not values:
        return

    get_user_settings(user_id)

    with connect() as conn:
        cursor = conn.cursor()
        columns = ", ".join(f"{key} = ?" for key in values)
        cursor.execute(
            f"UPDATE user_settings SET {columns} WHERE user_id = ?",
            (*values.values(), user_id),
        )


def clear_history(user_id):
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM history WHERE user_id = ?", (user_id,))


def add_history(user_id, url, file_type):
    history_enabled = get_user_settings(user_id)["history_enabled"]

    with connect() as conn:
        cursor = conn.cursor()
        user = cursor.execute(
            "SELECT username, first_name FROM users WHERE telegram_id = ?",
            (user_id,),
        ).fetchone()
        cursor.execute(
            """
            INSERT INTO downloads (
                telegram_id, username, first_name, url, media_type, status
            )
            VALUES (?, ?, ?, ?, ?, 'success')
            """,
            (
                user_id,
                user[0] if user else None,
                user[1] if user else None,
                url,
                file_type,
            ),
        )

        if not history_enabled:
            logger.info("Скачивание сохранено без пользовательской истории: %s", user_id)
            return

        cursor.execute(
            """
            INSERT INTO history (
                user_id,
                url,
                file_type
            )
            VALUES (?, ?, ?)
            """,
            (
                user_id,
                url,
                file_type,
            ),
        )

    logger.info("История сохранена! Записан user_id: %s", user_id)


def register_user(telegram_id, username, first_name, language_code=None):
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO users(
                telegram_id,
                username,
                first_name,
                registered_at,
                referral_eligible
            )
            VALUES(?,?,?, datetime('now'), 1)
            """,
            (
                telegram_id,
                username,
                first_name,
            ),
        )
        is_new_user = cursor.rowcount == 1
        cursor.execute(
            """
            UPDATE users
            SET username = ?,
                first_name = ?,
                language_code = ?,
                registered_at = COALESCE(registered_at, datetime('now')),
                last_seen_at = datetime('now')
            WHERE telegram_id = ?
            """,
            (
                username,
                first_name,
                language_code,
                telegram_id,
            ),
        )
    return is_new_user


def can_download(telegram_id):
    today = date.today().isoformat()

    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                is_premium,
                premium_until,
                downloads_today,
                last_download_date,
                bonus_downloads_remaining
            FROM users
            WHERE telegram_id = ?
            """,
            (telegram_id,),
        )

        row = cursor.fetchone()

        if row is None:
            return True

        is_premium, premium_until, downloads_today, last_download_date, bonus_remaining = row

        if _premium_is_active(conn, telegram_id, is_premium, premium_until):
            return True

        if last_download_date != today:
            cursor.execute(
                """
                UPDATE users
                SET downloads_today = 0,
                    last_download_date = ?
                WHERE telegram_id = ?
                """,
                (
                    today,
                    telegram_id,
                ),
            )
            downloads_today = 0

        return downloads_today < FREE_DAILY_LIMIT or bonus_remaining > 0


def increase_download_count(telegram_id):
    today = date.today().isoformat()

    with connect() as conn:
        conn.execute(
            "UPDATE users SET downloads_today = 0, last_download_date = ? WHERE telegram_id = ? AND last_download_date != ?",
            (today, telegram_id, today),
        )
        user = conn.execute(
            "SELECT is_premium, premium_until, downloads_today, bonus_downloads_remaining FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if user:
            is_premium, premium_until, downloads_today, bonus_remaining = user
            premium_active = _premium_is_active(conn, telegram_id, is_premium, premium_until)
            if not premium_active and downloads_today >= FREE_DAILY_LIMIT and bonus_remaining > 0:
                conn.execute(
                    "UPDATE users SET bonus_downloads_remaining = bonus_downloads_remaining - 1 WHERE telegram_id = ?",
                    (telegram_id,),
                )
            else:
                conn.execute(
                    "UPDATE users SET downloads_today = downloads_today + 1, last_download_date = ? WHERE telegram_id = ?",
                    (today, telegram_id),
                )
        referral = conn.execute(
            "SELECT referrer_user_id FROM referrals WHERE invited_user_id = ? AND qualified = 0",
            (telegram_id,),
        ).fetchone()
        if referral:
            conn.execute(
                "UPDATE referrals SET qualified = 1, qualified_at = datetime('now') WHERE invited_user_id = ? AND qualified = 0",
                (telegram_id,),
            )
            if conn.execute("SELECT changes()").fetchone()[0]:
                conn.execute(
                    "UPDATE users SET bonus_downloads_remaining = bonus_downloads_remaining + 5, bonus_downloads_total = bonus_downloads_total + 5 WHERE telegram_id = ?",
                    (referral[0],),
                )


def claim_referral(invited_user_id: int, referrer_user_id: int) -> bool:
    if invited_user_id == referrer_user_id:
        return False
    with connect() as conn:
        if conn.execute("SELECT 1 FROM users WHERE telegram_id = ?", (referrer_user_id,)).fetchone() is None:
            return False
        cursor = conn.execute(
            "UPDATE users SET referral_eligible = 0 WHERE telegram_id = ? AND referral_eligible = 1",
            (invited_user_id,),
        )
        if cursor.rowcount != 1:
            return False
        conn.execute(
            "INSERT OR IGNORE INTO referrals(invited_user_id, referrer_user_id) VALUES (?, ?)",
            (invited_user_id, referrer_user_id),
        )
        return conn.execute("SELECT changes()").fetchone()[0] == 1


def get_referral_stats(user_id: int) -> tuple[int, int, int]:
    with connect() as conn:
        invited, qualified = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(qualified), 0) FROM referrals WHERE referrer_user_id = ?",
            (user_id,),
        ).fetchone()
        bonus = conn.execute(
            "SELECT bonus_downloads_remaining FROM users WHERE telegram_id = ?",
            (user_id,),
        ).fetchone()
    return int(invited or 0), int(qualified or 0), int(bonus[0] if bonus else 0)


def get_user_total_downloads(telegram_id: int):
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM history WHERE user_id = ?",
            (telegram_id,),
        )
        count = cursor.fetchone()[0]

    return int(count or 0)


def has_feedback(user_id: int):
    with connect() as conn:
        return conn.execute("SELECT 1 FROM feedback WHERE user_id = ?", (user_id,)).fetchone() is not None


def save_feedback_rating(user_id: int, rating: int):
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO feedback(user_id, rating) VALUES (?, ?)",
            (user_id, rating),
        )


def get_inactive_users(after_days: int = 7, limit: int = 100):
    after_days = max(1, int(after_days))
    limit = max(1, min(int(limit), 1000))
    with connect() as conn:
        return conn.execute(
            """
            SELECT telegram_id, first_name, username FROM users
            WHERE COALESCE(reminders_enabled, 1) = 1
              AND last_seen_at IS NOT NULL
              AND datetime(last_seen_at) <= datetime('now', ?)
              AND (last_reminder_at IS NULL OR datetime(last_reminder_at) <= datetime('now', ?))
            ORDER BY datetime(last_seen_at) ASC LIMIT ?
            """,
            (f"-{after_days} days", f"-{after_days} days", limit),
        ).fetchall()


def mark_reminder_sent(telegram_id: int):
    with connect() as conn:
        conn.execute("UPDATE users SET last_reminder_at = datetime('now') WHERE telegram_id = ?", (telegram_id,))


def set_reminders_enabled(telegram_id: int, enabled: bool):
    with connect() as conn:
        conn.execute("UPDATE users SET reminders_enabled = ? WHERE telegram_id = ?", (int(bool(enabled)), telegram_id))


def get_bot_setting(key: str, default=None):
    with connect() as conn:
        row = conn.execute(
            "SELECT setting_value FROM bot_settings WHERE setting_key = ?", (key,)
        ).fetchone()
    return row[0] if row else default


def update_bot_setting(key: str, value):
    with connect() as conn:
        conn.execute(
            "INSERT INTO bot_settings(setting_key, setting_value) VALUES (?, ?) "
            "ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value",
            (key, str(value)),
        )


def get_reminder_settings():
    enabled = get_bot_setting("reminders_enabled", "1") == "1"
    try:
        after_days = max(1, int(str(get_bot_setting("reminder_after_days", "7"))))
    except (TypeError, ValueError):
        after_days = 7
    with connect() as conn:
        sent_total = conn.execute(
            "SELECT COUNT(*) FROM users WHERE last_reminder_at IS NOT NULL"
        ).fetchone()[0]
        sent_today = conn.execute(
            "SELECT COUNT(*) FROM users WHERE date(last_reminder_at) = date('now')"
        ).fetchone()[0]
    return {"enabled": enabled, "after_days": after_days, "sent_total": sent_total or 0, "sent_today": sent_today or 0}


def save_feedback_comment(user_id: int, comment: str):
    with connect() as conn:
        conn.execute(
            "UPDATE feedback SET comment = ? WHERE user_id = ?",
            (comment, user_id),
        )


def create_bonus_download_request(user_id, username, first_name):
    today = date.today().isoformat()

    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id
            FROM bonus_requests
            WHERE user_id = ?
              AND request_date = ?
              AND status IN ('pending', 'approved')
            """,
            (user_id, today),
        )
        if cursor.fetchone():
            return None

        cursor.execute(
            """
            INSERT INTO bonus_requests (
                user_id,
                username,
                first_name,
                request_date,
                status
            )
            VALUES (?, ?, ?, ?, 'pending')
            """,
            (user_id, username, first_name, today),
        )
        return cursor.lastrowid


def has_active_bonus_request(user_id):
    today = date.today().isoformat()

    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 1
            FROM bonus_requests
            WHERE user_id = ?
              AND request_date = ?
              AND status IN ('pending', 'approved')
            """,
            (user_id, today),
        )
        return cursor.fetchone() is not None


def get_bonus_request(request_id):
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, user_id, username, first_name, request_date, status, bonus_downloads, approved_by, approved_at
            FROM bonus_requests
            WHERE id = ?
            """,
            (request_id,),
        )
        return cursor.fetchone()


def approve_bonus_request(request_id, bonus_downloads, approved_by):
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id FROM bonus_requests WHERE id = ?",
            (request_id,),
        )
        request = cursor.fetchone()
        if not request:
            return False

        user_id = request[0]
        cursor.execute(
            """
            UPDATE bonus_requests
            SET status = 'approved',
                bonus_downloads = ?,
                approved_by = ?,
                approved_at = datetime('now')
            WHERE id = ?
            """,
            (bonus_downloads, approved_by, request_id),
        )
        cursor.execute(
            """
            UPDATE users
            SET bonus_downloads_remaining = bonus_downloads_remaining + ?,
                bonus_downloads_total = bonus_downloads_total + ?
            WHERE telegram_id = ?
            """,
            (bonus_downloads, bonus_downloads, user_id),
        )
        return True


def decline_bonus_request(request_id, approved_by):
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE bonus_requests
            SET status = 'declined',
                approved_by = ?,
                approved_at = datetime('now')
            WHERE id = ?
            """,
            (approved_by, request_id),
        )
        return cursor.rowcount > 0


def get_user_profile(telegram_id: int):
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                first_name,
                username,
                is_premium,
                premium_until,
                downloads_today,
                registered_at,
                bonus_downloads_total,
                bonus_downloads_remaining
            FROM users
            WHERE telegram_id = ?
            """,
            (telegram_id,),
        )
        profile = cursor.fetchone()
        if profile and profile[2] and not _premium_is_active(conn, telegram_id, profile[2], profile[3]):
            profile = (*profile[:2], 0, None, *profile[4:])

    return profile


def get_admin_stats():
    today = date.today().isoformat()
    with connect() as conn:
        users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        downloads_today = conn.execute(
            "SELECT COALESCE(SUM(downloads_today), 0) FROM users"
        ).fetchone()[0]
        history_today = conn.execute(
            "SELECT COUNT(*) FROM history WHERE date(created_at) = ?",
            (today,),
        ).fetchone()[0]
        premium_users = conn.execute(
            "SELECT COUNT(*) FROM users WHERE is_premium = 1 AND (premium_until IS NULL OR datetime(premium_until) > datetime('now', 'localtime'))"
        ).fetchone()[0]

    return {
        "users": int(users or 0),
        "downloads_today": int(downloads_today or 0),
        "history_today": int(history_today or 0),
        "premium_users": int(premium_users or 0),
    }


def get_admin_dashboard_stats():
    with connect() as conn:
        row = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM users),
                (SELECT COUNT(*) FROM users WHERE datetime(last_seen_at) >= datetime('now', '-1 day')),
                (SELECT COUNT(*) FROM users WHERE date(registered_at) = date('now')),
                (SELECT COUNT(*) FROM users WHERE date(registered_at) >= date('now', '-6 days')),
                (SELECT COUNT(*) FROM downloads WHERE date(created_at) = date('now')),
                (SELECT COUNT(*) FROM downloads WHERE date(created_at) >= date('now', '-6 days')),
                (SELECT COUNT(*) FROM downloads WHERE date(created_at) >= date('now', '-29 days'))
            """
        ).fetchone()
        services = conn.execute(
            """
            SELECT COALESCE(media_type, 'Неизвестно'), COUNT(*)
            FROM downloads
            WHERE date(created_at) >= date('now', '-29 days')
            GROUP BY media_type
            ORDER BY COUNT(*) DESC
            LIMIT 5
            """
        ).fetchall()

    return {
        "users": int(row[0] or 0),
        "active_24h": int(row[1] or 0),
        "new_today": int(row[2] or 0),
        "new_7d": int(row[3] or 0),
        "downloads_today": int(row[4] or 0),
        "downloads_7d": int(row[5] or 0),
        "downloads_30d": int(row[6] or 0),
        "services": [(str(name), int(count)) for name, count in services],
    }


def get_download_stats_by_service():
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT media_type, COUNT(*)
            FROM downloads
            GROUP BY media_type
            ORDER BY COUNT(*) DESC
            """
        ).fetchall()
    return [(str(media_type or "Неизвестно"), int(count)) for media_type, count in rows]


def get_admin_downloads_page(page: int = 0, limit: int = 10, service: str | None = None, user_id: int | None = None):
    """Fetch successful download records for the admin-only journal."""
    page = max(0, int(page))
    offset = page * limit
    conditions = ["status = 'success'"]
    params: list[object] = []
    if service:
        conditions.append("lower(COALESCE(media_type, '')) LIKE ?")
        params.append(f"%{service.lower()}%")
    if user_id is not None:
        conditions.append("telegram_id = ?")
        params.append(int(user_id))
    where = " AND ".join(conditions)

    with connect() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM downloads WHERE {where}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT telegram_id, username, first_name, url, media_type, created_at
            FROM downloads WHERE {where}
            ORDER BY id DESC LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        ).fetchall()
    return rows, int(total or 0)


def find_admin_download_users(query: str, limit: int = 10):
    """Search registered users by exact numeric ID or username/name prefix."""
    query = query.strip().lstrip("@")
    if not query:
        return []
    with connect() as conn:
        if query.isdigit():
            rows = conn.execute(
                "SELECT telegram_id, username, first_name FROM users WHERE telegram_id = ? LIMIT ?",
                (int(query), limit),
            ).fetchall()
        else:
            escaped = query.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            rows = conn.execute(
                """
                SELECT telegram_id, username, first_name FROM users
                WHERE lower(username) LIKE ? ESCAPE '\\' OR lower(first_name) LIKE ? ESCAPE '\\'
                ORDER BY lower(username), telegram_id LIMIT ?
                """,
                (f"{escaped}%", f"{escaped}%", limit),
            ).fetchall()
    return rows


def get_admin_user_download_summary(user_id: int):
    with connect() as conn:
        user = conn.execute(
            "SELECT telegram_id, username, first_name, is_premium, premium_until, registered_at FROM users WHERE telegram_id = ?",
            (user_id,),
        ).fetchone()
        if user and user[3] and not _premium_is_active(conn, user_id, user[3], user[4]):
            user = (*user[:3], 0, None, user[5])
        downloads = conn.execute(
            "SELECT COUNT(*), MAX(created_at) FROM downloads WHERE telegram_id = ? AND status = 'success'",
            (user_id,),
        ).fetchone()
    return (user, int(downloads[0] or 0), downloads[1]) if user else None


def preview_premium_expiry(user_id: int, days: int):
    if days not in {7, 30, 90}:
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT is_premium, premium_until FROM users WHERE telegram_id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        now = datetime.now()
        is_active = _premium_is_active(conn, user_id, row[0], row[1])
        if is_active and not row[1]:
            return None
        current_expiry = _premium_expiry(row[1]) if is_active else None
        start = current_expiry if current_expiry and current_expiry > now else now
        return (start + timedelta(days=days)).isoformat(sep=" ", timespec="seconds")


def update_user_premium(user_id: int, days: int | None, actor_id: int):
    """Grant/extend Premium or revoke it, recording the action in the same transaction."""
    if days is not None and days not in {7, 30, 90}:
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT username, first_name, is_premium, premium_until FROM users WHERE telegram_id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            return None

        username, first_name, current_flag, current_until = row
        now = datetime.now()
        active = _premium_is_active(conn, user_id, current_flag, current_until)
        if days is None:
            conn.execute(
                "UPDATE users SET is_premium = 0, premium_until = NULL WHERE telegram_id = ?",
                (user_id,),
            )
            event = "PREMIUM_REVOKED"
            details = f"Администратор {actor_id} отключил Premium"
            expiry_text = None
        else:
            if active and not current_until:
                return {"error": "permanent"}
            current_expiry = _premium_expiry(current_until) if active else None
            base = current_expiry if current_expiry and current_expiry > now else now
            expiry = base + timedelta(days=days)
            expiry_text = expiry.isoformat(sep=" ", timespec="seconds")
            conn.execute(
                "UPDATE users SET is_premium = 1, premium_until = ? WHERE telegram_id = ?",
                (expiry_text, user_id),
            )
            event = "PREMIUM_GRANTED"
            details = f"Администратор {actor_id} выдал/продлил Premium на {days} дней; до {expiry_text}"

        conn.execute(
            "INSERT INTO security_log(telegram_id, username, first_name, action, details, actor_id) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, first_name, event, details, actor_id),
        )
        return {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "is_premium": days is not None,
            "premium_until": expiry_text,
            "event": event,
        }


def get_recent_users(limit: int = 10):
    with connect() as conn:
        return conn.execute(
            """
            SELECT telegram_id, username, first_name, is_premium,
                   downloads_today, registered_at
            FROM users
            WHERE COALESCE(hidden_from_admin, 0) = 0
            ORDER BY COALESCE(registered_at, '') DESC, telegram_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def get_hidden_users(limit: int = 50):
    with connect() as conn:
        return conn.execute(
            """SELECT telegram_id, username, first_name, is_premium, downloads_today, registered_at
               FROM users WHERE hidden_from_admin = 1
               ORDER BY COALESCE(registered_at, '') DESC, telegram_id DESC LIMIT ?""",
            (min(100, max(1, int(limit))),),
        ).fetchall()


def is_user_hidden(telegram_id: int) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(hidden_from_admin, 0) FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
    return bool(row and row[0])


def set_user_hidden(telegram_id: int, hidden: bool, actor_id: int) -> bool:
    """Hide or restore a user in the admin list without deleting their data."""
    action = "ADMIN_USER_HIDDEN" if hidden else "ADMIN_USER_UNHIDDEN"
    with connect() as conn:
        cursor = conn.execute(
            "UPDATE users SET hidden_from_admin = ? WHERE telegram_id = ?",
            (int(hidden), telegram_id),
        )
        if cursor.rowcount:
            username, first_name = conn.execute(
                "SELECT username, first_name FROM users WHERE telegram_id = ?", (telegram_id,)
            ).fetchone()
            conn.execute(
                "INSERT INTO security_log(telegram_id, username, first_name, action, details, actor_id) VALUES (?, ?, ?, ?, '', ?)",
                (telegram_id, username, first_name, action, actor_id),
            )
        return cursor.rowcount > 0


def get_registered_user_ids():
    """Return Telegram IDs eligible for an owner initiated news broadcast."""
    with connect() as conn:
        return [row[0] for row in conn.execute(
            "SELECT telegram_id FROM users ORDER BY telegram_id"
        ).fetchall()]


def get_user_by_username(username: str):
    normalized = username.strip().lstrip("@").lower()
    if not normalized:
        return None
    with connect() as conn:
        return conn.execute(
            """
            SELECT telegram_id, username, first_name, is_premium,
                   downloads_today, registered_at
            FROM users
            WHERE lower(username) = ?
            LIMIT 1
            """,
            (normalized,),
        ).fetchone()


def get_recent_security_events(limit: int = 15):
    with connect() as conn:
        return conn.execute(
            """
            SELECT telegram_id, action, details, created_at
            FROM security_log
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


ADMIN_AUDIT_ACTIONS = (
    "PREMIUM_GRANTED", "PREMIUM_REVOKED", "USER_BANNED", "USER_UNBANNED",
    "ADMIN_ADDED", "ADMIN_REMOVED", "ADMIN_USER_HIDDEN", "ADMIN_USER_UNHIDDEN",
)


def get_admin_audit_page(page: int = 0, limit: int = 10, user_id: int | None = None):
    """Return account/role changes made by admins, optionally for one target user."""
    page = max(0, int(page))
    limit = min(50, max(1, int(limit)))
    placeholders = ",".join("?" for _ in ADMIN_AUDIT_ACTIONS)
    where = f"action IN ({placeholders})"
    params = list(ADMIN_AUDIT_ACTIONS)
    if user_id is not None:
        where += " AND telegram_id = ?"
        params.append(int(user_id))
    with connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM security_log WHERE {where}", params).fetchone()[0]
        rows = conn.execute(
            f"""SELECT telegram_id, username, first_name, action, details, actor_id, created_at
                FROM security_log WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?""",
            [*params, limit, page * limit],
        ).fetchall()
    return rows, total


def is_user_banned(telegram_id: int) -> bool:
    with connect() as conn:
        return conn.execute(
            "SELECT 1 FROM banned_users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone() is not None


def ban_user(telegram_id: int, banned_by: int, reason: str = ""):
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO banned_users(telegram_id, reason, banned_by) VALUES (?, ?, ?)",
            (telegram_id, reason[:500], banned_by),
        )
        user = conn.execute("SELECT username, first_name FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        conn.execute(
            "INSERT INTO security_log(telegram_id, username, first_name, action, details, actor_id) VALUES (?, ?, ?, 'USER_BANNED', ?, ?)",
            (telegram_id, *(user or (None, None)), reason[:500], banned_by),
        )


def unban_user(telegram_id: int, actor_id: int | None = None) -> bool:
    with connect() as conn:
        cursor = conn.execute(
            "DELETE FROM banned_users WHERE telegram_id = ?",
            (telegram_id,),
        )
        if cursor.rowcount:
            user = conn.execute("SELECT username, first_name FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            conn.execute(
                "INSERT INTO security_log(telegram_id, username, first_name, action, details, actor_id) VALUES (?, ?, ?, 'USER_UNBANNED', '', ?)",
                (telegram_id, *(user or (None, None)), actor_id),
            )
        return cursor.rowcount > 0


def get_banned_users(limit: int = 50):
    with connect() as conn:
        return conn.execute(
            "SELECT telegram_id, reason, banned_at FROM banned_users ORDER BY banned_at DESC LIMIT ?",
            (limit,),
        ).fetchall()


def add_bot_admin(telegram_id: int, added_by: int) -> bool:
    with connect() as conn:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO bot_admins(telegram_id, role, added_by) VALUES (?, 'admin', ?)",
            (telegram_id, added_by),
        )
        changed = cursor.rowcount > 0
        if changed:
            user = conn.execute("SELECT username, first_name FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            conn.execute(
                "INSERT INTO security_log(telegram_id, username, first_name, action, details, actor_id) VALUES (?, ?, ?, 'ADMIN_ADDED', '', ?)",
                (telegram_id, *(user or (None, None)), added_by),
            )
        return changed


def remove_bot_admin(telegram_id: int, actor_id: int | None = None) -> bool:
    with connect() as conn:
        cursor = conn.execute(
            "DELETE FROM bot_admins WHERE telegram_id = ?",
            (telegram_id,),
        )
        changed = cursor.rowcount > 0
        if changed:
            user = conn.execute("SELECT username, first_name FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            conn.execute(
                "INSERT INTO security_log(telegram_id, username, first_name, action, details, actor_id) VALUES (?, ?, ?, 'ADMIN_REMOVED', '', ?)",
                (telegram_id, *(user or (None, None)), actor_id),
            )
        return changed


def get_bot_admins():
    with connect() as conn:
        return conn.execute(
            "SELECT telegram_id, role, added_by, added_at FROM bot_admins ORDER BY added_at"
        ).fetchall()


def is_bot_admin(telegram_id: int) -> bool:
    with connect() as conn:
        return conn.execute(
            "SELECT 1 FROM bot_admins WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone() is not None
