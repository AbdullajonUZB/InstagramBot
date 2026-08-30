import shutil
import tempfile
import time
from pathlib import Path

from config import BOT_TOKEN, PROJECT_ROOT


STALE_TEMP_PREFIXES = ("instagram_bot_", "download_followup_", "video_tools_")


def cleanup_stale_temp_files(max_age_hours: int = 24):
    temp_root = Path(tempfile.gettempdir())
    cutoff = time.time() - max_age_hours * 3600
    removed = 0

    for path in temp_root.iterdir():
        if not path.name.startswith(STALE_TEMP_PREFIXES):
            continue
        try:
            if path.stat().st_mtime < cutoff:
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)
                removed += 1
        except OSError:
            continue
    return removed


def startup_checks():
    warnings = []
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не найден в .env")

    if not (PROJECT_ROOT / "database" / "history.db").exists():
        warnings.append("База данных будет создана при запуске")

    cookies_path = PROJECT_ROOT / "cookies.txt"
    if not cookies_path.exists():
        warnings.append("cookies.txt не найден: Instagram Stories могут быть недоступны")
    elif "sessionid" not in cookies_path.read_text(encoding="utf-8", errors="ignore"):
        warnings.append("В cookies.txt нет sessionid: приватные Instagram Stories недоступны")

    ffmpeg = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    ffprobe = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
    if not ffmpeg:
        warnings.append("ffmpeg не найден: MP3 и обработка видео недоступны")
    if not ffprobe:
        warnings.append("ffprobe не найден: извлечение кадров видео недоступно")
    return warnings
