import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from utils.logger import logger
from utils.message_utils import get_message_target
from utils.user_locks import get_user_lock


class VideoToolsHandler:
    MAX_VIDEO_SIZE_BYTES = 50 * 1024 * 1024

    def __init__(self):
        local_app_data = os.environ.get("LOCALAPPDATA")
        winget_dir = (
            os.path.join(local_app_data, "Microsoft", "WinGet", "Links")
            if local_app_data
            else None
        )
        self.ffmpeg_path = (
            shutil.which("ffmpeg")
            or shutil.which("ffmpeg.exe")
            or (os.path.join(winget_dir, "ffmpeg.exe") if winget_dir else None)
        )

        self.ffprobe_path = (
            shutil.which("ffprobe")
            or shutil.which("ffprobe.exe")
            or (os.path.join(winget_dir, "ffprobe.exe") if winget_dir else None)
        )
        print("FFmpeg:", self.ffmpeg_path)
        print("FFprobe:", self.ffprobe_path)
        
    async def handle_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = get_message_target(update)
        if message is None:
            return

        context.user_data["video_tools"] = True
        await message.reply_text("📤 Отправьте видеофайл")

    async def handle_video_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.user_data.get("video_tools"):
            return

        message = update.message
        if message is None or message.video is None:
            target = get_message_target(update)
            if target is not None:
                await target.reply_text("📤 Отправьте видеофайл")
            return

        lock = await get_user_lock(context, update.effective_user.id)
        async with lock:
            await self._handle_video_message_locked(update, context, message)

    async def _handle_video_message_locked(self, update, context, message):

        video = message.video
        print("FILE SIZE =", video.file_size)
        print("LIMIT =", self.MAX_VIDEO_SIZE_BYTES)
        file_size = getattr(video, "file_size", None)
        logger.info("Received video with size: %s bytes", file_size if file_size is not None else "unknown")

        if file_size is not None and file_size > self.MAX_VIDEO_SIZE_BYTES:
            logger.warning("Rejected video larger than limit: %s bytes", file_size)
            await message.reply_text(
                "❌ Видео слишком большое для обработки.\n"
                "Максимальный размер: 50 МБ"
            )
            return

        temp_dir = Path(tempfile.mkdtemp(prefix="video_tools_", dir=tempfile.gettempdir()))

        suffix = ".mp4"
        if video.file_name:
            suffix = Path(video.file_name).suffix or suffix

        source_path = temp_dir / f"source_video{suffix}"
        try:
            file = await video.get_file()
        except BadRequest as exc:
            logger.warning("Telegram rejected video download request: %s", exc)
            shutil.rmtree(temp_dir, ignore_errors=True)
            await message.reply_text(
                "❌ Не удалось получить видео от Telegram."
                " Попробуйте отправить файл меньшего размера."
            )
            return
        except Exception:
            logger.exception("Failed to fetch video file from Telegram")
            shutil.rmtree(temp_dir, ignore_errors=True)
            await message.reply_text("❌ Не удалось обработать видео. Попробуйте ещё раз.")
            return

        try:
            await file.download_to_drive(custom_path=str(source_path))
        except BadRequest as exc:
            logger.warning("Telegram rejected video download: %s", exc)
            shutil.rmtree(temp_dir, ignore_errors=True)
            await message.reply_text(
                "❌ Не удалось скачать видео от Telegram."
                " Попробуйте отправить файл меньшего размера."
            )
            return
        except Exception:
            logger.exception("Failed to download video file to disk")
            shutil.rmtree(temp_dir, ignore_errors=True)
            await message.reply_text("❌ Не удалось сохранить видео на сервере. Попробуйте ещё раз.")
            return

        context.user_data["video_tools_file"] = str(source_path)
        context.user_data["video_tools_temp_dir"] = str(temp_dir)

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🎵 Извлечь MP3", callback_data="video_tools:extract_mp3"),
                    InlineKeyboardButton("📸 Извлечь кадр", callback_data="video_tools:extract_frame"),
                ],
                [
                    InlineKeyboardButton("🎬 Сжать видео", callback_data="video_tools:compress_video"),
                    InlineKeyboardButton("❌ Отмена", callback_data="video_tools:cancel"),
                ],
            ]
        )

        await message.reply_text(
            "🎬 Видео готово. Выберите действие:",
            reply_markup=keyboard,
        )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if query is None or not query.data:
            return

        await query.answer()
        action = query.data.split(":", 1)[1]

        if action == "cancel":
            self._cleanup(context)
            await query.message.reply_text("❌ Операция отменена.")
            return

        file_path = context.user_data.get("video_tools_file")
        if not file_path:
            await query.message.reply_text("⚠️ Видео не найдено. Отправьте его заново.")
            return

        input_path = Path(file_path)
        if not input_path.exists():
            await query.message.reply_text("⚠️ Видео не найдено. Отправьте его заново.")
            return

        lock = await get_user_lock(context, update.effective_user.id)
        async with lock:
            try:
                if action == "extract_mp3":
                    await self._extract_mp3(query.message, input_path, context)
                elif action == "extract_frame":
                    await self._extract_frame(query.message, input_path, context)
                elif action == "compress_video":
                    await self._compress_video(query.message, input_path, context)
                else:
                    await query.message.reply_text("⚠️ Неизвестное действие.")
            except Exception as exc:
                await query.message.reply_text(f"❌ Ошибка: {exc}")

    async def _extract_mp3(self, message, input_path: Path, context: ContextTypes.DEFAULT_TYPE):
        if not self.ffmpeg_path:
            raise RuntimeError("ffmpeg не найден в системе")

        output_path = Path(context.user_data["video_tools_temp_dir"]) / "audio.mp3"
        command = [
            self.ffmpeg_path,
            "-y",
            "-i",
            str(input_path),
            "-vn",
            "-acodec",
            "libmp3lame",
            "-q:a",
            "2",
            str(output_path),
        ]
        await self._run_ffmpeg(command)
        await message.reply_audio(
            audio=InputFile(output_path.open("rb"), filename=output_path.name),
            caption="🎵 MP3 готов",
        )
        self._cleanup(context)

    async def _extract_frame(self, message, input_path: Path, context: ContextTypes.DEFAULT_TYPE):
        if not self.ffmpeg_path or not self.ffprobe_path:
            raise RuntimeError("ffmpeg или ffprobe не найден в системе")

        duration = await self._get_duration(input_path)
        position = duration / 2 if duration else 1.0
        output_path = Path(context.user_data["video_tools_temp_dir"]) / "frame.jpg"

        command = [
            self.ffmpeg_path,
            "-y",
            "-ss",
            str(position),
            "-i",
            str(input_path),
            "-frames:v",
            "1",
            str(output_path),
        ]
        await self._run_ffmpeg(command)
        await message.reply_photo(
            photo=InputFile(output_path.open("rb"), filename=output_path.name),
            caption="📸 Кадр из середины видео",
        )
        self._cleanup(context)

    async def _compress_video(self, message, input_path: Path, context: ContextTypes.DEFAULT_TYPE):
        if not self.ffmpeg_path:
            raise RuntimeError("ffmpeg не найден в системе")

        output_path = Path(context.user_data["video_tools_temp_dir"]) / "compressed.mp4"
        command = [
            self.ffmpeg_path,
            "-y",
            "-i",
            str(input_path),
            "-vcodec",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-acodec",
            "aac",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        await self._run_ffmpeg(command)
        await message.reply_video(
            video=InputFile(output_path.open("rb"), filename=output_path.name),
            caption="🎬 Видео сжато",
        )
        self._cleanup(context)

    async def _run_ffmpeg(self, command: list[str]):
        result = await asyncio.to_thread(
            subprocess.run,
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            error_text = (result.stderr or result.stdout or "ffmpeg failed").strip()
            raise RuntimeError(error_text[:1000])

    async def _get_duration(self, input_path: Path):
        if not self.ffprobe_path:
            return None

        command = [
            self.ffprobe_path,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(input_path),
        ]
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                command,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return None

        if result.returncode != 0:
            return None

        try:
            return float(result.stdout.strip())
        except ValueError:
            return None

    def _cleanup(self, context: ContextTypes.DEFAULT_TYPE):
        temp_dir = context.user_data.get("video_tools_temp_dir")
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)

        context.user_data.pop("video_tools_file", None)
        context.user_data.pop("video_tools_temp_dir", None)
