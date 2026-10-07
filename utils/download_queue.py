"""Bounded in-process download queue with safe cancellation of waiting jobs."""

import asyncio
import time
import uuid

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


MAX_CONCURRENT_DOWNLOADS = 2


async def run_queued_download(context, status_message, download_coro, owner_id=None):
    """Run a download with a process-wide concurrency cap.

    Only jobs that have not started can be cancelled; cancelling a running
    yt-dlp worker thread could race its temporary-file cleanup.
    """
    data = context.application.bot_data
    semaphore = data.setdefault(
        "download_semaphore", asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
    )
    waiting = data.setdefault("download_queue_waiting", {})
    job_id = uuid.uuid4().hex[:12]
    task = asyncio.current_task()
    is_waiting = semaphore.locked()
    loop = asyncio.get_running_loop()
    last_percent = {"value": -10, "edited_at": 0.0}

    def report_progress(progress):
        if progress.get("status") != "downloading":
            return
        total = progress.get("total_bytes") or progress.get("total_bytes_estimate")
        downloaded = progress.get("downloaded_bytes")
        if not total or not downloaded:
            return
        percent = min(100, int(downloaded * 100 / total))
        now = time.monotonic()
        if percent < last_percent["value"] + 10 and now - last_percent["edited_at"] < 5:
            return
        last_percent.update(value=percent, edited_at=now)

        async def edit_progress():
            try:
                await status_message.edit_text(f"⏳ Скачивание: {percent}%...")
            except Exception:
                pass

        loop.call_soon_threadsafe(lambda: asyncio.create_task(edit_progress()))

    if is_waiting:
        waiting[job_id] = {"task": task, "message": status_message, "owner_id": owner_id}
        try:
            position = len(waiting)
            await status_message.edit_text(
                f"🕒 Загрузка в очереди (примерно №{position}). Можно отменить ожидание.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                    "✖️ Отменить ожидание", callback_data=f"download_job:cancel:{job_id}"
                )]]),
            )
        except Exception:
            pass

    try:
        async with semaphore:
            waiting.pop(job_id, None)
            context.user_data["download_progress_callback"] = report_progress
            try:
                await status_message.edit_text("⏳ Скачивание началось...")
            except Exception:
                pass
            return await download_coro
    except asyncio.CancelledError:
        if is_waiting:
            waiting.pop(job_id, None)
            close = getattr(download_coro, "close", None)
            if close:
                close()
            try:
                await status_message.reply_text("✅ Ожидание отменено. Можете отправить ссылку снова.")
            except Exception:
                pass
            return False
        raise
    finally:
        waiting.pop(job_id, None)
        context.user_data.pop("download_progress_callback", None)


async def cancel_queued_download(update, context):
    query = update.callback_query
    if query is None or not query.data:
        return
    _, action, job_id = query.data.split(":", 2)
    job = context.application.bot_data.get("download_queue_waiting", {}).get(job_id)
    if (
        action != "cancel"
        or not job
        or job["task"].done()
        or (job.get("owner_id") is not None and query.from_user.id != job["owner_id"])
    ):
        await query.answer("Задача уже началась или завершилась.", show_alert=True)
        return
    await query.answer("Ожидание отменяется…")
    job["task"].cancel()
