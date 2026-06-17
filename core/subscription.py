from __future__ import annotations

import asyncio
import base64
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import aiohttp

from config import settings
from core.storage import Storage, SubscriptionRow

if TYPE_CHECKING:
    from core.manager import ProxyManager

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    url: str
    success: bool
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

    async def fetch(self, url: str) -> tuple[list[str], str]:
        """Returns (links, error). links is empty on error."""
        timeout = aiohttp.ClientTimeout(total=settings.SUBSCRIPTION_TIMEOUT)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=timeout,
                    headers={"User-Agent": "v2rayN/6.0"},
                ) as resp:
                    if resp.status != 200:
                        return [], f"HTTP {resp.status}"
                    body = await resp.text(encoding="utf-8", errors="replace")

            text = self._decode_body(body)
            links = [
                line.strip()
                for line in text.splitlines()
                if line.strip().startswith("vless://")
            ]
            return links, ""

        except asyncio.TimeoutError:
            return [], f"timeout after {settings.SUBSCRIPTION_TIMEOUT}s"
        except Exception as exc:
            return [], str(exc)


class SubscriptionManager:
    def __init__(self, storage: Storage, proxy_manager: "ProxyManager") -> None:
        self._storage = storage
        self._proxy_manager = proxy_manager
        self._fetcher = SubscriptionFetcher()
        self._tasks: dict[int, asyncio.Task] = {}

    async def startup(self) -> None:
        for url in settings.SUBSCRIPTION_URLS:
            await self._storage.add_subscription(
                url, fetch_interval=settings.SUBSCRIPTION_FETCH_INTERVAL
            )

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

    async def refresh_all(self) -> list[FetchResult]:
        subs = await self._storage.list_subscriptions()
        results = []
        for sub in subs:
            results.append(await self.refresh(sub.id))
        return results

    async def refresh(self, sub_id: int) -> FetchResult:
        from core.parser import parse_vless_list

        sub = await self._storage.get_subscription(sub_id)
        if sub is None:
            return FetchResult(url="", success=False, count=0, error="not found")

        logger.info("refreshing subscription %d: %s", sub_id, sub.url)
        links, error = await self._fetcher.fetch(sub.url)

        if error:
            logger.warning("subscription %d fetch failed: %s", sub_id, error)
            await self._storage.update_subscription_fetch(sub_id, 0, success=False)
            return FetchResult(url=sub.url, success=False, count=0, error=error)

        if not links:
            logger.warning("subscription %d returned no vless:// links", sub_id)
            await self._storage.update_subscription_fetch(sub_id, 0, success=True)
            return FetchResult(url=sub.url, success=True, count=0)

        valid_configs, _ = parse_vless_list("\n".join(links))
        if not valid_configs:
            await self._storage.update_subscription_fetch(sub_id, 0, success=True)
            return FetchResult(url=sub.url, success=True, count=0)

        await self._storage.replace_subscription_proxies(sub_id, valid_configs)
        await self._storage.update_subscription_fetch(sub_id, len(valid_configs), success=True)
        logger.info("subscription %d refreshed: %d proxies", sub_id, len(valid_configs))

        self._proxy_manager._create_task(
            self._proxy_manager._check_pending_and_reorder()
        )

        for proxy in await self._storage.get_all_proxies():
            if proxy.subscription_id == sub_id and proxy.status == "dead":
                if self._proxy_manager.process_pool.get_process(proxy.id) is not None:
                    await self._proxy_manager.process_pool.stop_proxy(proxy.id)

        return FetchResult(url=sub.url, success=True, count=len(valid_configs))

    def _start_poller(self, sub: SubscriptionRow) -> None:
        async def poller() -> None:
            if sub.last_fetch:
                wait = max(0.0, settings.SUBSCRIPTION_FETCH_INTERVAL - (time.time() - sub.last_fetch))
            else:
                wait = 0.0

            while True:
                if wait > 0:
                    await asyncio.sleep(wait)
                try:
                    await self.refresh(sub.id)
                    updated = await self._storage.get_subscription(sub.id)
                    if updated:
                        sub.last_fetch = updated.last_fetch
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error("subscription %d poller error: %s", sub.id, exc)
                wait = settings.SUBSCRIPTION_FETCH_INTERVAL

        task = asyncio.create_task(poller())
        self._tasks[sub.id] = task
