import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from config import settings
from core.health import HealthChecker, HealthResult, vless_config_from_proxy
from core.storage import PoolStats, ProxyRow, Storage
from core.subscription import SubscriptionManager
from core.xray import XrayProcessPool

logger = logging.getLogger(__name__)


@dataclass
class ProxyInfo:
    proxy_id: int
    name: str
    host: str
    port: int
    local_port: int
    latency_ms: int | None
    last_check: float | None


@dataclass
class ManagerStatus:
    pool_stats: PoolStats
    active_proxies: list[ProxyInfo]
    uptime_seconds: float


class ProxyManager:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self.process_pool = XrayProcessPool(storage)
        self.health_checker = HealthChecker(storage)
        self.subscription_manager = SubscriptionManager(storage, self)
        self._lock = asyncio.Lock()
        self._health_task: asyncio.Task | None = None
        self._started_at: float = time.time()
        self._background_tasks: set[asyncio.Task] = set()
        self.notify_callback: Callable[[ProxyRow, HealthResult], Awaitable[None]] | None = None
        self._last_notified: dict[int, bool] = {}

    def _create_task(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def startup(self) -> None:
        await self.storage.init()
        self._started_at = time.time()
        await self.subscription_manager.startup()

        self._health_task = asyncio.create_task(self._health_loop())

    async def shutdown(self) -> None:
        await self.subscription_manager.shutdown()

        if self._health_task is not None:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass

        for task in list(self._background_tasks):
            task.cancel()
        await asyncio.gather(*self._background_tasks, return_exceptions=True)

        await self.process_pool.stop_all()
        await self.storage.close()
        logger.info("manager shut down")

    async def _check_pending_and_reorder(self) -> None:
        await self.health_checker.check_pending(
            on_status_change=self._status_change_callback
        )
        await self._reorder_by_latency()

    async def _reorder_by_latency(self) -> None:
        async with self._lock:
            active = await self.storage.get_active_proxies()
            if not active:
                return

            sorted_proxies = sorted(
                active,
                key=lambda p: (p.latency_ms is None, p.latency_ms or 0),
            )
            ports = list(range(settings.PROXY_PORT_START, settings.PROXY_PORT_END + 1))
            desired = {proxy.id: ports[i] for i, proxy in enumerate(sorted_proxies) if i < len(ports)}

            moves: list[tuple[ProxyRow, int]] = []
            for proxy in sorted_proxies:
                new_port = desired.get(proxy.id)
                if new_port is None:
                    continue
                proc = self.process_pool.get_process(proxy.id)
                current_port = proc.local_port if proc else None
                if current_port != new_port:
                    moves.append((proxy, new_port))

            if not moves:
                return

            logger.info("reordering %d proxies by latency", len(moves))
            for proxy, _ in moves:
                if self.process_pool.get_process(proxy.id) is not None:
                    await self.process_pool.stop_proxy(proxy.id)
            for proxy, new_port in moves:
                config = vless_config_from_proxy(proxy)
                await self.process_pool.start_proxy(proxy.id, config, port=new_port)

    def _status_change_callback(self, result: HealthResult) -> None:
        asyncio.create_task(self._on_health_change(result))

    async def _on_health_change(self, result: HealthResult) -> None:
        proxy = await self.storage.get_proxy_by_id(result.proxy_id)
        if proxy is None:
            return

        async with self._lock:
            if result.success:
                if self.process_pool.get_process(result.proxy_id) is None:
                    config = vless_config_from_proxy(proxy)
                    await self.process_pool.start_proxy(result.proxy_id, config)
            else:
                if self.process_pool.get_process(result.proxy_id) is not None:
                    await self.process_pool.stop_proxy(result.proxy_id)

        prev_success = self._last_notified.get(result.proxy_id)
        status_changed = prev_success is not None and prev_success != result.success
        self._last_notified[result.proxy_id] = result.success

        if status_changed and self.notify_callback and settings.TG_NOTIFY_CHAT_ID:
            try:
                await self.notify_callback(proxy, result)
            except Exception as exc:
                logger.warning("notify_callback failed: %s", exc)

    async def get_status(self) -> ManagerStatus:
        pool_stats = await self.storage.get_stats()
        active_proxies = await self.storage.get_active_proxies()

        proxy_infos: list[ProxyInfo] = []
        for proxy in active_proxies:
            process = await self.storage.get_process(proxy.id)
            if process is None or process.status != "running":
                continue
            proxy_infos.append(
                ProxyInfo(
                    proxy_id=proxy.id,
                    name=proxy.name,
                    host=proxy.host,
                    port=proxy.port,
                    local_port=process.local_port,
                    latency_ms=proxy.latency_ms,
                    last_check=proxy.last_check,
                )
            )

        proxy_infos.sort(key=lambda p: p.local_port)

        return ManagerStatus(
            pool_stats=pool_stats,
            active_proxies=proxy_infos,
            uptime_seconds=time.time() - self._started_at,
        )

    async def force_recheck(self) -> None:
        self._create_task(self._run_full_check())

    async def _health_loop(self) -> None:
        cycle = 0
        while True:
            await asyncio.sleep(settings.CHECK_INTERVAL)
            logger.info("health check cycle %d", cycle)
            await self.health_checker.check_all_active(
                on_status_change=self._status_change_callback
            )
            await self.health_checker.check_pending(
                on_status_change=self._status_change_callback
            )
            if cycle % 3 == 0:
                logger.info("rechecking dead proxies (cycle %d)", cycle)
                await self.health_checker.check_dead(
                    on_status_change=self._status_change_callback
                )
            await self._reorder_by_latency()
            cycle += 1

    async def _run_full_check(self) -> None:
        await self.health_checker.check_all_active(
            on_status_change=self._status_change_callback
        )
        await self.health_checker.check_pending(
            on_status_change=self._status_change_callback
        )
        await self._reorder_by_latency()
