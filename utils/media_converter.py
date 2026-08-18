import asyncio
import os
import shutil
import subprocess
from pathlib import Path


def get_ffmpeg_path():
    local_app_data = os.environ.get("LOCALAPPDATA")
    winget_path = (
        Path(local_app_data) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"
        if local_app_data
        else None
    )
    return shutil.which("ffmpeg") or shutil.which("ffmpeg.exe") or (
        str(winget_path) if winget_path and winget_path.exists() else None
    )


async def convert_video_to_mp3(input_path: Path, output_path: Path):
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError("ffmpeg не найден в системе")

    result = await asyncio.to_thread(
        subprocess.run,
        [ffmpeg, "-y", "-i", str(input_path), "-vn", "-acodec", "libmp3lame", "-q:a", "2", str(output_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not output_path.exists():
        error = (result.stderr or result.stdout or "MP3 conversion failed").strip()
        raise RuntimeError(error[:1000])
