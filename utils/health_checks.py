import asyncio
import ssl
import time
from urllib.parse import urlsplit

from config import TELEGRAM_LOCAL_API_URL


SERVICE_HOSTS = (
    ("Instagram", "www.instagram.com"),
    ("YouTube", "www.youtube.com"),
    ("Pinterest", "www.pinterest.com"),
    ("Facebook", "www.facebook.com"),
)


def _telegram_api_target():
    if TELEGRAM_LOCAL_API_URL:
        parts = urlsplit(TELEGRAM_LOCAL_API_URL)
        host = parts.hostname
        if host:
            return "Локальный Telegram API", host, parts.port or 80, parts.scheme == "https"
    return "Telegram Bot API", "api.telegram.org", 443, True


async def _probe_connection(host: str, port: int, use_tls: bool, timeout: float = 4.0):
    started = time.perf_counter()
    writer = None
    try:
        connect = asyncio.open_connection(
            host,
            port,
            ssl=ssl.create_default_context() if use_tls else None,
            server_hostname=host if use_tls else None,
        )
        _, writer = await asyncio.wait_for(connect, timeout=timeout)
        return round((time.perf_counter() - started) * 1000)
    except (OSError, ssl.SSLError, asyncio.TimeoutError):
        return None
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass


async def collect_service_pings():
    api_name, api_host, api_port, api_tls = _telegram_api_target()
    targets = [(api_name, api_host, api_port, api_tls)] + [
        (name, host, 443, True) for name, host in SERVICE_HOSTS
    ]
    results = await asyncio.gather(
        *(
            _probe_connection(host, port, use_tls)
            for _, host, port, use_tls in targets
        )
    )
    return [(name, latency) for (name, *_), latency in zip(targets, results)]


def format_service_ping(name: str, latency_ms: int | None) -> str:
    if latency_ms is None:
        return f"🔴 {name}: нет соединения"
    return f"🟢 {name}: {latency_ms} мс"
