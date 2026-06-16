from __future__ import annotations

import asyncio
import base64
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import aiohttp

from config import settings
from core.storage import Storage, SubscriptionRow, SubscriptionStats

if TYPE_CHECKING:
    from core.manager import ProxyManager

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    url: str
    success: bool
    links: list[str]
    count: int
    error: str = ""


class SubscriptionFetcher:
    @staticmethod
    def _decode_body(body: str) -> str:
        try:
            body_clean = body.strip().replace("\n", "").replace("\r", "").rstrip("=")
            body_clean += "=" * (-len(body_clean) % 4)
            for decode in (base64.b64decode, base64.urlsafe_b64decode):
                try:
                    decoded = decode(body_clean).decode("utf-8")
                    if "vless://" in decoded:
                        return decoded
                except Exception:
                    continue
        except Exception:
            pass
        return body

    async def fetch(self, url: str) -> FetchResult:
        timeout = aiohttp.ClientTimeout(total=settings.SUBSCRIPTION_TIMEOUT)
        headers = {"User-Agent": "v2rayN/6.0"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=timeout, headers=headers) as resp:
                    if resp.status != 200:
                        return FetchResult(
                            url=url,
                            success=False,
                            links=[],
                            count=0,
                            error=f"HTTP {resp.status}",
                        )
                    body = await resp.text(encoding="utf-8", errors="replace")

            text = self._decode_body(body)
            links = [
                line.strip()
                for line in text.splitlines()
                if line.strip().startswith("vless://")
            ]
            return FetchResult(url=url, success=True, links=links, count=len(links))

        except asyncio.TimeoutError:
            return FetchResult(
                url=url,
                success=False,
                links=[],
                count=0,
                error=f"timeout after {settings.SUBSCRIPTION_TIMEOUT}s",
            )
        except Exception as exc:
            return FetchResult(url=url, success=False, links=[], count=0, error=str(exc))


class SubscriptionManager:
    def __init__(self, storage: Storage, proxy_manager: "ProxyManager") -> None:
        self._storage = storage
        self._proxy_manager = proxy_manager
        self._fetcher = SubscriptionFetcher()
        self._tasks: dict[int, asyncio.Task] = {}

    async def startup(self) -> None:
        subs = await self._storage.list_subscriptions()
        for sub in subs:
            self._start_poller(sub)
        logger.info("subscription manager started: %d subscriptions", len(subs))

    async def shutdown(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()

    async def add_subscription(
        self, url: str, name: str = "", fetch_interval: int | None = None
    ) -> tuple[int, FetchResult]:
        interval = fetch_interval if fetch_interval is not None else settings.SUBSCRIPTION_FETCH_INTERVAL
        sub_id = await self._storage.add_subscription(url, name, interval)
        result = await self.refresh_subscription(sub_id)
        if sub_id not in self._tasks:
            sub = await self._storage.get_subscription(sub_id)
            if sub:
                self._start_poller(sub)
        return sub_id, result

    async def add_or_refresh(self, url: str) -> FetchResult:
        existing = await self._storage.get_subscription_by_url(url)
        if existing:
            return await self.refresh_subscription(existing.id)
        _, result = await self.add_subscription(url)
        return result

    async def refresh_subscription(self, sub_id: int) -> FetchResult:
        from core.parser import parse_vless_list

        sub = await self._storage.get_subscription(sub_id)
        if sub is None:
            return FetchResult(url="", success=False, links=[], count=0, error="not found")

        logger.info("refreshing subscription %d: %s", sub_id, sub.url)
        result = await self._fetcher.fetch(sub.url)

        if not result.success:
            logger.warning("subscription %d fetch failed: %s", sub_id, result.error)
            await self._storage.update_subscription_fetch(sub_id, 0, success=False)
            return result

        if not result.links:
            logger.warning("subscription %d returned no vless:// links", sub_id)
            await self._storage.update_subscription_fetch(sub_id, 0, success=True)
            return result

        valid_configs, _ = parse_vless_list("\n".join(result.links))
        if valid_configs:
            await self._storage.replace_subscription_proxies(sub_id, valid_configs)
            await self._storage.update_subscription_fetch(sub_id, len(valid_configs), success=True)
            logger.info("subscription %d refreshed: %d proxies", sub_id, len(valid_configs))
            self._proxy_manager._create_task(
                self._proxy_manager.health_checker.check_pending(
                    on_status_change=self._proxy_manager._status_change_callback
                )
            )
        else:
            await self._storage.update_subscription_fetch(sub_id, 0, success=True)

        result.count = len(valid_configs) if valid_configs else 0
        return result

    async def refresh_all(self) -> list[FetchResult]:
        subs = await self._storage.list_subscriptions()
        results = []
        for sub in subs:
            results.append(await self.refresh_subscription(sub.id))
        return results

    async def remove_subscription(self, sub_id: int) -> None:
        task = self._tasks.pop(sub_id, None)
        if task:
            task.cancel()
        await self._storage.delete_subscription_proxies(sub_id)
        await self._storage.delete_subscription(sub_id)

    async def get_subscription(self, sub_id: int) -> SubscriptionRow | None:
        return await self._storage.get_subscription(sub_id)

    async def list_subscriptions(self) -> list[SubscriptionStats]:
        return await self._storage.list_subscription_stats()

    def _start_poller(self, sub: SubscriptionRow) -> None:
        async def poller() -> None:
            while True:
                if sub.last_fetch:
                    elapsed = time.time() - sub.last_fetch
                    wait = max(0.0, sub.fetch_interval - elapsed)
                else:
                    wait = float(sub.fetch_interval)

                await asyncio.sleep(wait)

                try:
                    await self.refresh_subscription(sub.id)
                    updated = await self._storage.get_subscription(sub.id)
                    if updated:
                        sub.fetch_interval = updated.fetch_interval
                        sub.last_fetch = updated.last_fetch
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error("subscription %d poller error: %s", sub.id, exc)

        task = asyncio.create_task(poller())
        self._tasks[sub.id] = task
