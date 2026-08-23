"""Create a consistent SQLite backup and remove backups older than 14 days."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATABASE = ROOT / "database" / "history.db"
BACKUP_DIR = ROOT / "backups"
RETENTION_SECONDS = 14 * 24 * 60 * 60


def main():
    if not DATABASE.exists():
        raise SystemExit(f"Database not found: {DATABASE}")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"history_{time.strftime('%Y%m%d_%H%M%S')}.db"

    with sqlite3.connect(DATABASE) as source, sqlite3.connect(backup_path) as target:
        source.backup(target)

    cutoff = time.time() - RETENTION_SECONDS
    for path in BACKUP_DIR.glob("history_*.db"):
        if path != backup_path and path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)

    print(f"Backup created: {backup_path}")


if __name__ == "__main__":
    main()
