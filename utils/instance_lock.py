"""Prevent accidentally starting two polling instances of the bot."""

import os
import tempfile
from pathlib import Path


class SingleInstanceLock:
    def __init__(self, name="instagram_bot_instance.lock"):
        self.path = Path(tempfile.gettempdir()) / name
        self._handle = None

    def acquire(self):
        self._handle = self.path.open("a+")
        self._handle.seek(0)
        self._handle.write("0")
        self._handle.flush()
        try:
            if os.name == "nt":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            self._handle.close()
            self._handle = None
            raise RuntimeError("Другой экземпляр бота уже запущен")
        return self

    def release(self):
        if self._handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, exc_type, exc_value, traceback):
        self.release()
