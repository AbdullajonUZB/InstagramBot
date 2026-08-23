import asyncio
import shutil
import subprocess
from pathlib import Path


def _tool(name: str):
    return shutil.which(name) or shutil.which(f"{name}.exe")


async def ensure_telegram_compatible_video(file_path: Path) -> Path:
    """Return an MP4 encoded as H.264/AAC for reliable mobile playback."""
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
    if codec == "h264" and file_path.suffix.lower() == ".mp4":
        return file_path

    output_path = file_path.with_name(f"{file_path.stem}_telegram.mp4")
    result = await asyncio.to_thread(
        subprocess.run,
        [ffmpeg, "-y", "-i", str(file_path), "-map", "0:v:0", "-map", "0:a?",
         "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-movflags", "+faststart", str(output_path)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0 or not output_path.exists():
        raise RuntimeError("Video transcoding for Telegram failed")
    file_path.unlink(missing_ok=True)
    return output_path
