import logging
import shutil
import tempfile
from abc import ABC
from pathlib import Path

from yt_dlp import YoutubeDL


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

    def download_media(self, output_template="%(title)s.%(ext)s", ytdlp_options=None):
        if self.temp_dir is None:
            self.prepare_temp_dir()

        output_path = self.temp_dir / output_template
        ytdlp_opts = {
            "outtmpl": str(output_path),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
        }
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

    def cleanup(self):
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.logger.debug("Removed temporary directory %s", self.temp_dir)
            self.temp_dir = None

