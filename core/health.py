import asyncio
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass

import aiohttp

from config import settings
from core.parser import VlessConfig
from core.storage import ProxyRow, Storage
from core.xray import write_xray_config

logger = logging.getLogger(__name__)

# Port range reserved exclusively for health checks — never overlaps with pool
_CHECK_PORT_BASE = 19900
_SUCCESS_STATUSES = {200, 301, 302, 303, 307, 308, 403, 404, 429, 999}


@dataclass
class HealthResult:
    proxy_id: int
    success: bool
    latency_ms: int | None
    status_code: int | None
    error: str
    checked_at: float
    check_url: str


def vless_config_from_proxy(proxy: ProxyRow) -> VlessConfig:
    """Reconstruct VlessConfig from the params dict stored in ProxyRow."""
    return VlessConfig(**proxy.params)


def _failed(proxy_id: int, error: str, checked_at: float, check_url: str) -> HealthResult:
    return HealthResult(
        proxy_id=proxy_id,
        success=False,
        latency_ms=None,
        status_code=None,
        error=error,
        checked_at=checked_at,
        check_url=check_url,
    )


async def _check_tcp(host: str, port: int, timeout: float = 5.0) -> bool:
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


async def _check_proxy(proxy_id: int, vless_config: VlessConfig) -> HealthResult:
    checked_at = time.time()
    check_url = settings.CHECK_URL

    if not os.path.exists(settings.XRAY_BINARY):
        return _failed(proxy_id, f"xray binary not found at {settings.XRAY_BINARY}", checked_at, check_url)

    check_port = _CHECK_PORT_BASE + (proxy_id % 100)
    config_path = write_xray_config(vless_config, check_port, os.path.join(settings.XRAY_CONFIG_DIR, "health"))

    proc = await asyncio.create_subprocess_exec(
        settings.XRAY_BINARY, "run", "-config", config_path,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )

    try:
        await asyncio.sleep(settings.CHECK_STARTUP_XRAY_WAIT)

        if proc.returncode is not None:
            return _failed(proxy_id, f"xray exited early with code {proc.returncode}", checked_at, check_url)

        t0 = time.monotonic()
        connector = aiohttp.TCPConnector()
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(
                check_url,
                proxy=f"socks5://127.0.0.1:{check_port}",
                timeout=aiohttp.ClientTimeout(total=settings.CHECK_TIMEOUT),
                allow_redirects=False,
                headers={"User-Agent": "Mozilla/5.0"},
            ) as resp:
                status_code = resp.status

        latency_ms = int((time.monotonic() - t0) * 1000)
        success = status_code in _SUCCESS_STATUSES
        logger.debug(
            "health check proxy_id=%d host=%s status=%d latency=%dms success=%s",
            proxy_id, vless_config.host, status_code, latency_ms, success,
        )
        return HealthResult(
            proxy_id=proxy_id,
            success=success,
            latency_ms=latency_ms if success else None,
            status_code=status_code,
            error="" if success else f"unexpected status {status_code}",
            checked_at=checked_at,
            check_url=check_url,
        )

    except aiohttp.ClientError as exc:
        return _failed(proxy_id, str(exc), checked_at, check_url)
    except asyncio.TimeoutError:
        return _failed(proxy_id, f"timeout after {settings.CHECK_TIMEOUT}s", checked_at, check_url)
    finally:
        try:
            proc.terminate()
        except ProcessLookupError:
            pass
        if os.path.exists(config_path):
            os.remove(config_path)


class HealthChecker:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage
        self._semaphore = asyncio.Semaphore(5)

    async def check_one(
        self,
        proxy: ProxyRow,
        config: VlessConfig,
        on_status_change: Callable | None = None,
    ) -> HealthResult:
        tcp_ok = await _check_tcp(proxy.host, proxy.port)
        if not tcp_ok:
            logger.info("TCP check failed: proxy_id=%d host=%s port=%d", proxy.id, proxy.host, proxy.port)
            await self._storage.set_proxy_status(proxy.id, "dead")
            result = _failed(proxy.id, f"TCP connect failed to {proxy.host}:{proxy.port}", time.time(), settings.CHECK_URL)
            if on_status_change:
                on_status_change(result)
            return result

        result = await _check_proxy(proxy.id, config)

        if result.success:
            await self._storage.set_proxy_status(proxy.id, "active", result.latency_ms)
            logger.info("proxy alive: proxy_id=%d host=%s latency=%sms", proxy.id, proxy.host, result.latency_ms)
        else:
            await self._storage.set_proxy_status(proxy.id, "dead")
            updated = await self._storage.get_proxy_by_id(proxy.id)
            if updated and updated.fail_count >= 3:
                logger.warning(
                    "proxy appears permanently dead: proxy_id=%d host=%s fail_count=%d",
                    proxy.id, proxy.host, updated.fail_count,
                )
            logger.info("proxy dead: proxy_id=%d host=%s error=%s", proxy.id, proxy.host, result.error)

        if on_status_change:
            on_status_change(result)

        return result

    async def check_all_active(self, on_status_change: Callable | None = None) -> list[HealthResult]:
        return await self._check_batch(await self._storage.get_active_proxies(), on_status_change)

    async def check_pending(self, on_status_change: Callable | None = None) -> list[HealthResult]:
        return await self._check_batch(await self._storage.get_pending_proxies(), on_status_change)

    async def check_dead(self, on_status_change: Callable | None = None) -> list[HealthResult]:
        return await self._check_batch(await self._storage.get_dead_proxies(), on_status_change)

    async def _check_batch(
        self,
        proxies: list[ProxyRow],
        on_status_change: Callable | None = None,
    ) -> list[HealthResult]:
        async def _guarded(proxy: ProxyRow) -> HealthResult:
            async with self._semaphore:
                return await self.check_one(proxy, vless_config_from_proxy(proxy), on_status_change)

        results = await asyncio.gather(*[_guarded(p) for p in proxies], return_exceptions=True)

        out: list[HealthResult] = []
        for proxy, res in zip(proxies, results):
            if isinstance(res, Exception):
                logger.error("unexpected error checking proxy_id=%d: %s", proxy.id, res)
            else:
                out.append(res)
        return out
