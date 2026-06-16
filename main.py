import asyncio
import logging
import signal

import uvicorn

from api.server import create_api
from bot.bot import create_bot
from config import settings
from core.manager import ProxyManager
from core.storage import Storage
from core.watcher import FileWatcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def run() -> None:
    storage = Storage(settings.DB_PATH)
    manager = ProxyManager(storage)

    await manager.startup()

    bot, dp = create_bot(manager)
    api_app = create_api(manager)

    watcher = FileWatcher(manager)
    await watcher.load_once()
    asyncio.create_task(watcher.run_forever())

    uvicorn_config = uvicorn.Config(
        api_app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level="warning",
    )
    server = uvicorn.Server(uvicorn_config)
    server.install_signal_handlers = lambda: None

    logger.info(
        "API listening on http://%s:%d", settings.API_HOST, settings.API_PORT
    )

    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown.set)

    async def polling_loop() -> None:
        retry_delay = 5
        while True:
            try:
                await dp.start_polling(bot, allowed_updates=["message"])
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("bot polling error: %s, retrying in %ds", exc, retry_delay)
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)
            else:
                retry_delay = 5

    server_task = asyncio.create_task(server.serve())
    polling_task = asyncio.create_task(polling_loop())

    await shutdown.wait()
    logger.info("shutdown signal received")

    server.should_exit = True
    polling_task.cancel()

    try:
        await asyncio.wait_for(
            asyncio.gather(server_task, polling_task, return_exceptions=True),
            timeout=5.0,
        )
    except asyncio.TimeoutError:
        pass
    await bot.session.close()
    await manager.shutdown()
    logger.info("service stopped")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
