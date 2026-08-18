import shutil
import tempfile
from pathlib import Path


def clear_followup_media(context):
    media_dir = context.user_data.pop("followup_media_dir", None)
    context.user_data.pop("followup_media_path", None)
    if media_dir:
        shutil.rmtree(media_dir, ignore_errors=True)


def remember_video_for_mp3(context, source_path: Path):
    clear_followup_media(context)
    media_dir = Path(tempfile.mkdtemp(prefix="download_followup_"))
    cached_path = media_dir / "source_video"
    shutil.copy2(source_path, cached_path)
    context.user_data["followup_media_dir"] = str(media_dir)
    context.user_data["followup_media_path"] = str(cached_path)
