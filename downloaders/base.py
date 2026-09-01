import logging
import shutil
import os
import tempfile
from abc import ABC
from pathlib import Path
from typing import Any, cast
from yt_dlp import YoutubeDL
from utils.i18n import t
from utils.message_utils import require_effective_user, require_message_target


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".flv"}


def is_transient_download_error(error: Exception) -> bool:
    error_text = str(error).lower()
    return any(
        marker in error_text
        for marker in (
            "winerror 10060",
            "timed out",
            "timeout",
            "transporterror",
            "connection reset",
            "connection refused",
            "temporary failure",
        )
    )

class BaseDownloader(ABC):
    def __init__(self, url: str, logger: logging.Logger | None = None, temp_root: str | Path | None = None):
        self.url = url
        self.logger = logger or logging.getLogger(__name__)
        self.temp_root = Path(temp_root) if temp_root else Path(tempfile.gettempdir())
        self.temp_dir = None

    def prepare_temp_dir(self) -> Path:
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.temp_dir = Path(tempfile.mkdtemp(prefix="instagram_bot_", dir=self.temp_root))
        self.logger.debug("Created temporary directory %s", self.temp_dir)
        return self.temp_dir

    def download_media(
        self,
        output_template: str = "media_%(id)s.%(ext)s",
        ytdlp_options: dict[str, object] | None = None,
    ) -> Path:
        if self.temp_dir is None:
            self.prepare_temp_dir()

        assert self.temp_dir is not None
        output_path = self.temp_dir / output_template
        ytdlp_opts = {
            "outtmpl": str(output_path),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
        }
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            ytdlp_opts["ffmpeg_location"] = os.path.join(
                local_app_data, "Microsoft", "WinGet", "Links"
            )
        if ytdlp_options:
            ytdlp_opts.update(ytdlp_options)

        self.logger.debug("Downloading %s to %s with options %s", self.url, self.temp_dir, ytdlp_opts)
        try:
            with YoutubeDL(cast(Any, ytdlp_opts)) as ydl:
                info = ydl.extract_info(self.url, download=True)
                downloaded_file = Path(ydl.prepare_filename(info))
        except Exception as error:
            if is_transient_download_error(error):
                self.logger.warning("Temporary network failure downloading %s: %s", self.url, error)
            else:
                self.logger.exception("Failed to download media from %s", self.url)
            raise

        downloaded_files = [
            path for path in self.temp_dir.rglob("*")
            if path.is_file() and not path.name.endswith(".part")
        ]
        video_files = [
            path for path in downloaded_files
            if path.suffix.lower() in VIDEO_EXTENSIONS
        ]
        if video_files:
            downloaded_file = max(video_files, key=lambda path: path.stat().st_size)
        elif downloaded_files and not downloaded_file.exists():
            downloaded_file = max(downloaded_files, key=lambda path: path.stat().st_size)

        self.logger.debug("Download finished, file created at %s", downloaded_file)
        return downloaded_file

    def validate_file(self, file_path: Path, max_size: int | None = None) -> int:
        if not file_path.exists():
            raise FileNotFoundError("Downloaded file does not exist: %s" % file_path)

        size = file_path.stat().st_size
        if size == 0:
            raise ValueError("Downloaded file is empty: %s" % file_path)

        if max_size is not None and size > max_size:
            raise ValueError("Downloaded file exceeds maximum size: %s > %s" % (size, max_size))

        self.logger.debug("Validated downloaded file %s with size %s", file_path, size)
        return size

    def resolve_downloaded_file(self, filename: str | Path) -> Path | None:
        file_path = Path(filename)
        if file_path.exists() and file_path.suffix.lower() in VIDEO_EXTENSIONS:
            return file_path

        if self.temp_dir is not None and self.temp_dir.exists():
            files = [
                path for path in self.temp_dir.rglob("*")
                if path.is_file() and not path.name.endswith(".part")
            ]
            video_files = [
                path for path in files
                if path.suffix.lower() in VIDEO_EXTENSIONS
            ]
            if video_files:
                return max(video_files, key=lambda path: path.stat().st_size)
            if file_path.exists():
                return file_path
            return max(files, key=lambda path: path.stat().st_size) if files else None

        return file_path if file_path.exists() else None

    async def resolve_validated_file(
        self,
        update,
        filename: str | Path,
        max_size: int | None = None,
        missing_return: bool = False,
        too_large_return: bool = False,
        missing_key: str = "file_missing",
        too_large_key: str = "file_too_large",
        empty_key: str = "file_missing",
    ) -> tuple[Path | None, bool | None]:
        file_path = self.resolve_downloaded_file(filename)
        message = require_message_target(update)
        user = require_effective_user(update)
        if not file_path or not file_path.exists():
            await message.reply_text(t(user.id, missing_key))
            return None, missing_return

        try:
            self.validate_file(file_path, max_size=max_size)
        except FileNotFoundError:
            await message.reply_text(t(user.id, missing_key))
            return None, missing_return
        except ValueError as error:
            if "exceeds maximum size" in str(error):
                await message.reply_text(t(user.id, too_large_key))
                return None, too_large_return
            if "empty" in str(error):
                await message.reply_text(t(user.id, empty_key))
                return None, missing_return
            raise

        return file_path, None

    async def handle_error(
        self,
        update,
        error: Exception,
        error_key: str,
        logger_message: str,
        print_traceback: bool = False,
    ) -> None:
        if print_traceback:
            import traceback

            traceback.print_exc()

        self.logger.error("%s: %s", logger_message, error, exc_info=True)
        message = require_message_target(update)
        user = require_effective_user(update)
        await message.reply_text(t(user.id, error_key))

    def cleanup(self):
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.logger.debug("Removed temporary directory %s", self.temp_dir)
            self.temp_dir = None

