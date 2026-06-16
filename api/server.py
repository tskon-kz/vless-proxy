from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import settings
from core.manager import ProxyManager


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class ProxyResponse(BaseModel):
    protocol: str = "socks5"
    host: str
    port: int
    proxy_url: str
    name: str
    latency_ms: int | None
    last_check: float | None = None


class ProxyListResponse(BaseModel):
    count: int
    proxies: list[ProxyResponse]


class PoolStatsSchema(BaseModel):
    active: int
    dead: int
    pending: int
    invalid: int
    running_processes: int


class ProxyStatusDetail(BaseModel):
    name: str
    host: str
    status: str
    local_port: int
    latency_ms: int | None
    last_check: float | None
    fail_count: int


class StatusResponse(BaseModel):
    pool: PoolStatsSchema
    check_url: str
    check_interval_seconds: int
    uptime_seconds: float
    proxies: list[ProxyStatusDetail]


class UpdateRequest(BaseModel):
    links: list[str]


class UpdateResponse(BaseModel):
    total_received: int
    valid: int
    invalid: int
    newly_added: int
    removed: int
    errors: list[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _proxy_url(local_port: int) -> str:
    return f"socks5://{settings.PROXY_BIND_HOST}:{local_port}"


def _bearer_auth(request: Request) -> None:
    if not settings.API_SECRET_KEY:
        raise HTTPException(status_code=404)
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != settings.API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing Bearer token")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_api(manager: ProxyManager) -> FastAPI:
    app = FastAPI(title="VLESS Proxy Manager", docs_url=None, redoc_url=None)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/proxy/list", response_model=ProxyListResponse)
    async def proxy_list():
        status = await manager.get_status()
        proxies = [
            ProxyResponse(
                host=settings.PROXY_BIND_HOST,
                port=p.local_port,
                proxy_url=_proxy_url(p.local_port),
                name=p.name,
                latency_ms=p.latency_ms,
                last_check=p.last_check,
            )
            for p in status.active_proxies
        ]
        return ProxyListResponse(count=len(proxies), proxies=proxies)

    @app.get("/proxy/random", response_model=ProxyResponse)
    async def proxy_random():
        info = await manager.get_proxy_for_client()
        if info is None:
            return JSONResponse(
                status_code=503,
                content={"error": "no_active_proxies", "message": "No active proxies available"},
            )
        return ProxyResponse(
            host=settings.PROXY_BIND_HOST,
            port=info.local_port,
            proxy_url=_proxy_url(info.local_port),
            name=info.name,
            latency_ms=info.latency_ms,
            last_check=info.last_check,
        )

    @app.get("/proxy/best", response_model=ProxyResponse)
    async def proxy_best():
        status = await manager.get_status()
        candidates = [p for p in status.active_proxies if p.latency_ms is not None]
        if not candidates:
            return JSONResponse(
                status_code=503,
                content={"error": "no_active_proxies", "message": "No active proxies available"},
            )
        best = min(candidates, key=lambda p: p.latency_ms)  # type: ignore[arg-type]
        return ProxyResponse(
            host=settings.PROXY_BIND_HOST,
            port=best.local_port,
            proxy_url=_proxy_url(best.local_port),
            name=best.name,
            latency_ms=best.latency_ms,
            last_check=best.last_check,
        )

    @app.get("/status", response_model=StatusResponse)
    async def status():
        mgr_status = await manager.get_status()

        # Build detailed proxy list with fail_count from storage
        active_rows = await manager.storage.get_active_proxies()
        proxy_details: list[ProxyStatusDetail] = []
        for row in active_rows:
            process = await manager.storage.get_process(row.id)
            if process is None or process.status != "running":
                continue
            proxy_details.append(
                ProxyStatusDetail(
                    name=row.name,
                    host=row.host,
                    status=row.status,
                    local_port=process.local_port,
                    latency_ms=row.latency_ms,
                    last_check=row.last_check,
                    fail_count=row.fail_count,
                )
            )

        pool = mgr_status.pool_stats
        return StatusResponse(
            pool=PoolStatsSchema(
                active=pool.active,
                dead=pool.dead,
                pending=pool.pending,
                invalid=pool.invalid,
                running_processes=pool.running_processes,
            ),
            check_url=mgr_status.check_url,
            check_interval_seconds=settings.CHECK_INTERVAL,
            uptime_seconds=mgr_status.uptime_seconds,
            proxies=proxy_details,
        )

    @app.post("/update", response_model=UpdateResponse, dependencies=[Depends(_bearer_auth)])
    async def update(body: UpdateRequest):
        report = await manager.update_proxies(body.links, source="api")
        return UpdateResponse(
            total_received=report.total_received,
            valid=report.valid,
            invalid=report.invalid,
            newly_added=report.newly_added,
            removed=report.removed,
            errors=report.parse_errors,
        )

    return app
