import asyncio
import logging
import random
import time
from dataclasses import dataclass

from config import settings
from core.health import HealthChecker, HealthResult, vless_config_from_proxy
from core.parser import parse_vless, parse_vless_list
from core.storage import PoolStats, ProxyRow, Storage
from core.xray import XrayProcessPool

logger = logging.getLogger(__name__)


@dataclass
class UpdateReport:
    total_received: int
    valid: int
    invalid: int
    parse_errors: list[str]
    newly_added: int
    already_known: int
    removed: int
    source: str


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
    check_url: str
    uptime_seconds: float


class ProxyManager:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self.process_pool = XrayProcessPool(storage)
        self.health_checker = HealthChecker(storage)
        self._lock = asyncio.Lock()
        self._health_task: asyncio.Task | None = None
        self._started_at: float = time.time()
        self._background_tasks: set[asyncio.Task] = set()

    def _create_task(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def startup(self) -> None:
        await self.storage.init()
        self._started_at = time.time()

        active = await self.storage.get_active_proxies()
        restored = 0
        for proxy in active:
            config = vless_config_from_proxy(proxy)
            proc = await self.process_pool.start_proxy(proxy.id, config)
            if proc is not None:
                restored += 1

        logger.info("startup: restored %d/%d active proxies", restored, len(active))

        pending = await self.storage.get_pending_proxies()
        if pending:
            logger.info("startup: checking %d pending proxies", len(pending))
            self._create_task(
                self.health_checker.check_pending(
                    on_status_change=self._status_change_callback
                )
            )

        self._health_task = asyncio.create_task(
            self.health_checker.run_forever(
                on_status_change=self._status_change_callback
            )
        )

    async def shutdown(self) -> None:
        if self._health_task is not None:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass

        for task in list(self._background_tasks):
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

        await self.process_pool.stop_all()
        await self.storage.close()
        logger.info("manager shut down")

    async def update_proxies(
        self, raw_links: list[str], source: str
    ) -> UpdateReport:
        async with self._lock:
            total_received = len(raw_links)
            text = "\n".join(raw_links)
            valid_configs, all_results = parse_vless_list(text)

            parse_errors = [r.error for r in all_results if not r.success]
            valid = len(valid_configs)
            invalid = total_received - valid

            stats = await self.storage.replace_all(valid_configs, source)

            # Stop processes for proxies removed from the list
            all_proxies = await self.storage.get_all_proxies()
            dead_ids = {p.id for p in all_proxies if p.status == "dead"}
            for proxy_id in dead_ids:
                if self.process_pool.get_process(proxy_id) is not None:
                    await self.process_pool.stop_proxy(proxy_id)

            # Kick off health checks for pending proxies in the background
            pending = await self.storage.get_pending_proxies()
            if pending:
                self._create_task(
                    self.health_checker.check_pending(
                        on_status_change=self._status_change_callback
                    )
                )

            return UpdateReport(
                total_received=total_received,
                valid=valid,
                invalid=invalid,
                parse_errors=parse_errors,
                newly_added=stats.added,
                already_known=valid - stats.added,
                removed=stats.removed,
                source=source,
            )

    def _status_change_callback(self, result: HealthResult) -> None:
        asyncio.create_task(self._on_health_change(result))

    async def _on_health_change(self, result: HealthResult) -> None:
        proxy = await self.storage.get_proxy_by_id(result.proxy_id)
        if proxy is None:
            return

        if result.success:
            if self.process_pool.get_process(result.proxy_id) is None:
                config = vless_config_from_proxy(proxy)
                await self.process_pool.start_proxy(result.proxy_id, config)
        else:
            if self.process_pool.get_process(result.proxy_id) is not None:
                await self.process_pool.stop_proxy(result.proxy_id)

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

        return ManagerStatus(
            pool_stats=pool_stats,
            active_proxies=proxy_infos,
            check_url=settings.CHECK_URL,
            uptime_seconds=time.time() - self._started_at,
        )

    async def force_recheck(self) -> None:
        self._create_task(self._run_full_check())

    async def _run_full_check(self) -> None:
        await self.health_checker.check_all_active(
            on_status_change=self._status_change_callback
        )
        await self.health_checker.check_pending(
            on_status_change=self._status_change_callback
        )

    async def get_proxy_for_client(self) -> ProxyInfo | None:
        active = await self.storage.get_active_proxies()
        if not active:
            return None

        random.shuffle(active)
        for proxy in active:
            process = await self.storage.get_process(proxy.id)
            if process and process.status == "running":
                return ProxyInfo(
                    proxy_id=proxy.id,
                    name=proxy.name,
                    host=proxy.host,
                    port=proxy.port,
                    local_port=process.local_port,
                    latency_ms=proxy.latency_ms,
                    last_check=proxy.last_check,
                )
        return None
