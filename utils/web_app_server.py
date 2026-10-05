from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import web

from config import WEB_APP_HOST, WEB_APP_PORT, WEB_APP_URL
from utils.logger import logger

WEB_APP_DIR = Path(__file__).resolve().parent.parent / "webapp"


async def _index(_request):
    return web.FileResponse(WEB_APP_DIR / "index.html")


async def _health(_request):
    return web.json_response({"status": "ok"})


async def start_web_app_server(application):
    if not WEB_APP_URL:
        logger.info("Mini App disabled: set WEB_APP_URL to a public HTTPS address")
        return
    app_url = urlsplit(WEB_APP_URL)
    if app_url.scheme != "https" or not app_url.hostname:
        logger.warning("Mini App disabled: WEB_APP_URL must use HTTPS")
        return

    web_app = web.Application(client_max_size=16 * 1024)
    web_app.router.add_get("/", _index)
    web_app.router.add_get("/healthz", _health)
    web_app.router.add_static("/assets/", WEB_APP_DIR / "assets", show_index=False)
    runner = web.AppRunner(web_app, access_log=None)
    try:
        await runner.setup()
        site = web.TCPSite(runner, WEB_APP_HOST, WEB_APP_PORT)
        await site.start()
    except OSError:
        await runner.cleanup()
        logger.exception("Could not start Mini App web server")
        return

    application.bot_data["web_app_runner"] = runner
    logger.info("Mini App server listening on %s:%s for %s", WEB_APP_HOST, WEB_APP_PORT, WEB_APP_URL)


async def stop_web_app_server(application):
    runner = application.bot_data.pop("web_app_runner", None)
    if runner is not None:
        await runner.cleanup()
