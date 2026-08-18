"""Run the bot in development mode with automatic reload on Python changes."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
IGNORED_PARTS = {".git", ".venv", "__pycache__", "logs"}
POLL_INTERVAL = 0.5
RESTART_DELAY = 0.8


def source_files():
    return (
        path
        for path in ROOT.rglob("*.py")
        if not any(part in IGNORED_PARTS for part in path.relative_to(ROOT).parts)
    )


def snapshot():
    return {
        path: path.stat().st_mtime_ns
        for path in source_files()
        if path.is_file()
    }


def stop_process(process):
    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def start_bot():
    print("[dev] Starting bot...", flush=True)
    return subprocess.Popen([sys.executable, str(ROOT / "app.py")], cwd=ROOT)


def main():
    known_files = snapshot()
    process = start_bot()

    try:
        while True:
            time.sleep(POLL_INTERVAL)
            current_files = snapshot()

            if current_files != known_files:
                print("[dev] Python changes detected; restarting bot...", flush=True)
                stop_process(process)
                time.sleep(RESTART_DELAY)
                known_files = current_files
                process = start_bot()
            elif process.poll() is not None:
                print(
                    f"[dev] Bot exited with code {process.returncode}; restarting...",
                    flush=True,
                )
                time.sleep(RESTART_DELAY)
                process = start_bot()
    except KeyboardInterrupt:
        print("\n[dev] Stopping bot...", flush=True)
        stop_process(process)


if __name__ == "__main__":
    main()
