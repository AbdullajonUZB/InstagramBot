import asyncio
import shutil
import subprocess
import logging
from pathlib import Path


logger = logging.getLogger(__name__)


def _tool(name: str):
    return shutil.which(name) or shutil.which(f"{name}.exe")


async def ensure_telegram_compatible_video(file_path: Path) -> Path:
    """Normalize video geometry and encode H.264/AAC for reliable mobile playback."""
    ffprobe = _tool("ffprobe")
    ffmpeg = _tool("ffmpeg")
    if not ffprobe or not ffmpeg:
        return file_path

    probe = await asyncio.to_thread(
        subprocess.run,
        [ffprobe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1",
         str(file_path)],
        capture_output=True, text=True, check=False,
    )
    codec = probe.stdout.strip().lower()
    # Avoid a second conversion when a downloader already normalized the file.
    if codec == "h264" and file_path.suffix.lower() == ".mp4" and file_path.stem.endswith("_telegram"):
        return file_path

    output_path = file_path.with_name(f"{file_path.stem}_telegram.mp4")
    common_args = [
        ffmpeg, "-y", "-i", str(file_path), "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-map_metadata", "0", "-metadata:s:v:0", "rotate=0",
        "-movflags", "+faststart", str(output_path),
    ]
    result = await asyncio.to_thread(
        subprocess.run,
        [*common_args[:6], "-vf", "scale=trunc(iw*sar/2)*2:trunc(ih/2)*2,setsar=1", *common_args[6:]],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        logger.warning(
            "Video geometry normalization failed for %s; retrying without SAR filter: %s",
            file_path,
            result.stderr[-1000:].strip(),
        )
        result = await asyncio.to_thread(
            subprocess.run,
            [*common_args[:6], "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1", *common_args[6:]],
            capture_output=True, text=True, check=False,
        )
    if result.returncode != 0 or not output_path.exists():
        logger.error("FFmpeg failed for %s: %s", file_path, result.stderr[-1500:].strip())
        raise RuntimeError("Video transcoding for Telegram failed")
    file_path.unlink(missing_ok=True)
    return output_path
