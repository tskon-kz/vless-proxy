import asyncio
import logging
import signal

import uvicorn

from api.server import create_api
from config import settings
from core.manager import ProxyManager
from core.storage import Storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def run() -> None:
    storage = Storage(settings.DB_PATH)
    manager = ProxyManager(storage)

    await manager.startup()

    api_app = create_api(manager)
    uvicorn_config = uvicorn.Config(
        api_app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level="warning",
    )
    server = uvicorn.Server(uvicorn_config)

    loop = asyncio.get_running_loop()

    def _handle_signal():
        logger.info("shutdown signal received")
        server.should_exit = True

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal)

    logger.info(
        "API listening on http://%s:%d", settings.API_HOST, settings.API_PORT
    )

    try:
        await server.serve()
    finally:
        await manager.shutdown()
        logger.info("service stopped")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
