from fastapi import FastAPI
from fastapi.responses import JSONResponse

from config import settings
from core.manager import ProxyManager


def create_api(manager: ProxyManager) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None)

    @app.get("/proxy/best")
    async def proxy_best():
        """Returns the fastest proxy (always assigned to PROXY_PORT_START after reorder)."""
        all_ports = manager.process_pool.get_all_ports()
        if not all_ports:
            return JSONResponse(status_code=503, content={"error": "no active proxies"})

        port = settings.PROXY_PORT_START
        if port not in all_ports.values():
            port = min(all_ports.values())

        return {"url": f"socks5://{settings.PROXY_BIND_HOST}:{port}"}

    @app.get("/proxy/list")
    async def proxy_list():
        """Returns all active proxy URLs as a plain array."""
        all_ports = manager.process_pool.get_all_ports()
        return [
            f"socks5://{settings.PROXY_BIND_HOST}:{port}"
            for port in sorted(all_ports.values())
        ]

    return app
