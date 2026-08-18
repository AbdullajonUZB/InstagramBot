import logging
import shutil
import os
import tempfile
from abc import ABC
from pathlib import Path
from yt_dlp import YoutubeDL
from utils.i18n import t
from utils.message_utils import get_message_target

class BaseDownloader(ABC):
    def __init__(self, url, logger=None, temp_root=None):
        self.url = url
        self.logger = logger or logging.getLogger(__name__)
        self.temp_root = Path(temp_root) if temp_root else Path(tempfile.gettempdir())
        self.temp_dir = None

    def prepare_temp_dir(self):
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.temp_dir = Path(tempfile.mkdtemp(prefix="instagram_bot_", dir=self.temp_root))
        self.logger.debug("Created temporary directory %s", self.temp_dir)
        return self.temp_dir

    def download_media(self, output_template="media_%(id)s.%(ext)s", ytdlp_options=None):
        if self.temp_dir is None:
            self.prepare_temp_dir()

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
            with YoutubeDL(ytdlp_opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                downloaded_file = Path(ydl.prepare_filename(info))
        except Exception:
            self.logger.exception("Failed to download media from %s", self.url)
            raise

        self.logger.debug("Download finished, file created at %s", downloaded_file)
        return downloaded_file

    def validate_file(self, file_path, max_size=None):
        if not file_path.exists():
            raise FileNotFoundError("Downloaded file does not exist: %s" % file_path)

        size = file_path.stat().st_size
        if size == 0:
            raise ValueError("Downloaded file is empty: %s" % file_path)

        if max_size is not None and size > max_size:
            raise ValueError("Downloaded file exceeds maximum size: %s > %s" % (size, max_size))

        self.logger.debug("Validated downloaded file %s with size %s", file_path, size)
        return size

    def resolve_downloaded_file(self, filename):
        file_path = Path(filename)
        if file_path.exists():
            return file_path

        if self.temp_dir is not None and self.temp_dir.exists():
            files = [path for path in self.temp_dir.iterdir() if path.is_file()]
            return files[0] if files else None

        return None

    async def resolve_validated_file(
        self,
        update,
        filename,
        max_size=None,
        missing_return=False,
        too_large_return=False,
        missing_key="file_missing",
        too_large_key="file_too_large",
        empty_key="file_missing",
    ):
        file_path = self.resolve_downloaded_file(filename)
        message = get_message_target(update)
        if not file_path or not file_path.exists():
            await message.reply_text(t(update.effective_user.id, missing_key))
            return None, missing_return

        try:
            self.validate_file(file_path, max_size=max_size)
        except FileNotFoundError:
            await message.reply_text(t(update.effective_user.id, missing_key))
            return None, missing_return
        except ValueError as error:
            if "exceeds maximum size" in str(error):
                await message.reply_text(t(update.effective_user.id, too_large_key))
                return None, too_large_return
            if "empty" in str(error):
                await message.reply_text(t(update.effective_user.id, empty_key))
                return None, missing_return
            raise

        return file_path, None

    async def handle_error(self, update, error, error_key, logger_message, print_traceback=False):
        if print_traceback:
            import traceback

            traceback.print_exc()

        self.logger.error("%s: %s", logger_message, error, exc_info=True)
        message = get_message_target(update)
        await message.reply_text(t(update.effective_user.id, error_key))

    def cleanup(self):
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.logger.debug("Removed temporary directory %s", self.temp_dir)
            self.temp_dir = None

