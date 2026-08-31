import logging
import sqlite3
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

DB_NAME = str(Path(__file__).resolve().parent / "history.db")

FREE_DAILY_LIMIT = 20


def connect():
    Path(__file__).resolve().parent.mkdir(exist_ok=True)

    logger.debug("База: %s", Path(DB_NAME).resolve())

    conn = sqlite3.connect(DB_NAME, timeout=10)
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_column(conn, table_name, column_name, definition):
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    existing_columns = {row[1] for row in cursor.fetchall()}
    if column_name not in existing_columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


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

        _ensure_column(conn, "users", "registered_at", "TEXT")
        _ensure_column(conn, "users", "bonus_downloads_total", "INTEGER NOT NULL DEFAULT 0")


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
                details
            )
            VALUES(?,?,?,?,?)
            """,
            (
                telegram_id,
                username,
                first_name,
                action,
                details,
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
            SELECT send_format, history_enabled, language
            FROM user_settings
            WHERE user_id = ?
            """,
            (user_id,),
        )
        row = cursor.fetchone()

    send_format, history_enabled, language = row

    return {
        "send_format": send_format,
        "history_enabled": bool(history_enabled),
        "language": language,
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
    if not get_user_settings(user_id)["history_enabled"]:
        return

    with connect() as conn:
        cursor = conn.cursor()
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


def register_user(telegram_id, username, first_name):
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO users(
                telegram_id,
                username,
                first_name,
                registered_at
            )
            VALUES(?,?,?, datetime('now'))
            """,
            (
                telegram_id,
                username,
                first_name,
            ),
        )
        cursor.execute(
            """
            UPDATE users
            SET username = ?,
                first_name = ?,
                registered_at = COALESCE(registered_at, datetime('now'))
            WHERE telegram_id = ?
            """,
            (
                username,
                first_name,
                telegram_id,
            ),
        )


def can_download(telegram_id):
    today = date.today().isoformat()

    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                is_premium,
                downloads_today,
                last_download_date
            FROM users
            WHERE telegram_id = ?
            """,
            (telegram_id,),
        )

        row = cursor.fetchone()

        if row is None:
            return True

        is_premium, downloads_today, last_download_date = row

        if is_premium:
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

        return downloads_today < FREE_DAILY_LIMIT


def increase_download_count(telegram_id):
    today = date.today().isoformat()

    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE users
            SET downloads_today = downloads_today + 1,
                last_download_date = ?
            WHERE telegram_id = ?
            """,
            (
                today,
                telegram_id,
            ),
        )


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
    today = date.today().isoformat()

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
            SET downloads_today = downloads_today + ?,
                last_download_date = ?,
                bonus_downloads_total = bonus_downloads_total + ?
            WHERE telegram_id = ?
            """,
            (bonus_downloads, today, bonus_downloads, user_id),
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
                bonus_downloads_total
            FROM users
            WHERE telegram_id = ?
            """,
            (telegram_id,),
        )
        profile = cursor.fetchone()

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
            "SELECT COUNT(*) FROM users WHERE is_premium = 1"
        ).fetchone()[0]

    return {
        "users": int(users or 0),
        "downloads_today": int(downloads_today or 0),
        "history_today": int(history_today or 0),
        "premium_users": int(premium_users or 0),
    }


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


def unban_user(telegram_id: int) -> bool:
    with connect() as conn:
        cursor = conn.execute(
            "DELETE FROM banned_users WHERE telegram_id = ?",
            (telegram_id,),
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
        return cursor.rowcount > 0


def remove_bot_admin(telegram_id: int) -> bool:
    with connect() as conn:
        cursor = conn.execute(
            "DELETE FROM bot_admins WHERE telegram_id = ?",
            (telegram_id,),
        )
        return cursor.rowcount > 0


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
