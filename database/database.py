import logging
import sqlite3
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

DB_NAME = "database/history.db"

FREE_DAILY_LIMIT = 10


def connect():
    Path("database").mkdir(exist_ok=True)

    logger.debug("База: %s", Path(DB_NAME).resolve())

    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


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
                first_name
            )
            VALUES(?,?,?)
            """,
            (
                telegram_id,
                username,
                first_name,
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
                downloads_today
            FROM users
            WHERE telegram_id = ?
            """,
            (telegram_id,),
        )
        profile = cursor.fetchone()

    return profile