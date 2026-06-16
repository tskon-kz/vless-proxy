import asyncio
import base64
import os
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.subscription import FetchResult, SubscriptionFetcher, SubscriptionManager

VALID_URI = (
    "vless://9d507afd-7e90-4b7e-8bd8-6877f7a304ae@1.2.3.4:443"
    "?security=tls&type=tcp#Server1"
)
VALID_URI_2 = (
    "vless://aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee@5.6.7.8:443"
    "?security=tls&type=tcp#Server2"
)
SUB_URL = "https://sub.example.com/token"


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

@pytest.fixture
async def storage():
    from core.storage import Storage
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    s = Storage(db_path)
    await s.init()
    yield s
    await s.close()
    os.unlink(db_path)


def _mock_manager():
    mgr = MagicMock()
    mgr._create_task = MagicMock()
    mgr.health_checker.check_pending = AsyncMock()
    mgr._status_change_callback = MagicMock()
    return mgr


def _http(status: int = 200, body: str = "") -> patch:
    """Patch aiohttp.ClientSession to return the given status and body."""
    resp = MagicMock()
    resp.status = status
    resp.text = AsyncMock(return_value=body)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)

    session = MagicMock()
    session.get = MagicMock(return_value=resp)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    return patch("aiohttp.ClientSession", return_value=session)


def _http_raise(exc: Exception) -> patch:
    """Patch aiohttp.ClientSession to raise exc when entering the GET response."""
    resp = MagicMock()
    resp.__aenter__ = AsyncMock(side_effect=exc)
    resp.__aexit__ = AsyncMock(return_value=None)

    session = MagicMock()
    session.get = MagicMock(return_value=resp)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    return patch("aiohttp.ClientSession", return_value=session)


# ---------------------------------------------------------------------------
# SubscriptionFetcher._decode_body
# ---------------------------------------------------------------------------

class TestDecodeBody:
    def test_base64_with_vless_decoded(self):
        content = f"{VALID_URI}\n{VALID_URI_2}"
        encoded = base64.b64encode(content.encode()).decode()
        result = SubscriptionFetcher._decode_body(encoded)
        assert "vless://" in result
        assert result == content

    def test_plain_text_returned_as_is(self):
        plain = f"{VALID_URI}\n{VALID_URI_2}"
        result = SubscriptionFetcher._decode_body(plain)
        assert result == plain

    def test_base64_without_vless_returns_plain(self):
        content = "not a vless link at all"
        encoded = base64.b64encode(content.encode()).decode()
        result = SubscriptionFetcher._decode_body(encoded)
        assert result == encoded  # not decoded, plain text returned

    def test_invalid_base64_returns_plain(self):
        garbage = "!!!not_base64!!!"
        result = SubscriptionFetcher._decode_body(garbage)
        assert result == garbage

    def test_base64_with_newlines_stripped_before_decode(self):
        content = VALID_URI
        encoded = base64.b64encode(content.encode()).decode()
        # simulate line-wrapped base64
        wrapped = "\n".join(encoded[i:i+60] for i in range(0, len(encoded), 60))
        result = SubscriptionFetcher._decode_body(wrapped)
        assert "vless://" in result


# ---------------------------------------------------------------------------
# SubscriptionFetcher.fetch
# ---------------------------------------------------------------------------

class TestFetch:
    async def test_returns_links_from_plain_text(self):
        body = f"{VALID_URI}\n{VALID_URI_2}\nnot-a-link"
        fetcher = SubscriptionFetcher()
        with _http(200, body):
            result = await fetcher.fetch(SUB_URL)
        assert result.success is True
        assert result.count == 2
        assert len(result.links) == 2
        assert all(l.startswith("vless://") for l in result.links)

    async def test_returns_links_from_base64(self):
        content = f"{VALID_URI}\n{VALID_URI_2}"
        encoded = base64.b64encode(content.encode()).decode()
        fetcher = SubscriptionFetcher()
        with _http(200, encoded):
            result = await fetcher.fetch(SUB_URL)
        assert result.success is True
        assert result.count == 2

    async def test_non_200_returns_failure(self):
        fetcher = SubscriptionFetcher()
        with _http(404, ""):
            result = await fetcher.fetch(SUB_URL)
        assert result.success is False
        assert "404" in result.error
        assert result.links == []

    async def test_timeout_returns_failure(self):
        fetcher = SubscriptionFetcher()
        with patch("core.subscription.settings") as s:
            s.SUBSCRIPTION_TIMEOUT = 30
            with _http_raise(asyncio.TimeoutError()):
                result = await fetcher.fetch(SUB_URL)
        assert result.success is False
        assert "timeout" in result.error.lower()

    async def test_connection_error_returns_failure(self):
        fetcher = SubscriptionFetcher()
        with _http_raise(OSError("connection refused")):
            result = await fetcher.fetch(SUB_URL)
        assert result.success is False
        assert result.error != ""

    async def test_empty_response_returns_zero_links(self):
        fetcher = SubscriptionFetcher()
        with _http(200, "# just comments\nhello world"):
            result = await fetcher.fetch(SUB_URL)
        assert result.success is True
        assert result.count == 0
        assert result.links == []


# ---------------------------------------------------------------------------
# SubscriptionManager.refresh_subscription
# ---------------------------------------------------------------------------

class TestRefreshSubscription:
    async def test_sub_not_found_returns_error(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        result = await sm.refresh_subscription(9999)
        assert result.success is False
        assert "not found" in result.error

    async def test_fetch_failure_increments_fail_count(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        sub_id = await storage.add_subscription(SUB_URL, "", 3600)

        with _http(503, ""):
            await sm.refresh_subscription(sub_id)

        sub = await storage.get_subscription(sub_id)
        assert sub.fail_count == 1
        assert sub.last_fetch is None  # not updated on failure

    async def test_fetch_success_no_links_updates_db(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        sub_id = await storage.add_subscription(SUB_URL, "", 3600)

        with _http(200, "no vless links here"):
            await sm.refresh_subscription(sub_id)

        sub = await storage.get_subscription(sub_id)
        assert sub.fail_count == 0
        assert sub.last_fetch is not None  # updated even with zero links

    async def test_fetch_success_replaces_subscription_proxies(self, storage):
        mock_mgr = _mock_manager()
        sm = SubscriptionManager(storage, mock_mgr)
        sub_id = await storage.add_subscription(SUB_URL, "", 3600)

        body = f"{VALID_URI}\n{VALID_URI_2}"
        with _http(200, body):
            result = await sm.refresh_subscription(sub_id)

        assert result.success is True
        all_proxies = await storage.get_all_proxies()
        sub_proxies = [p for p in all_proxies if p.subscription_id == sub_id]
        assert len(sub_proxies) == 2

    async def test_fetch_success_kicks_health_check(self, storage):
        mock_mgr = _mock_manager()
        sm = SubscriptionManager(storage, mock_mgr)
        sub_id = await storage.add_subscription(SUB_URL, "", 3600)

        with _http(200, VALID_URI):
            await sm.refresh_subscription(sub_id)

        mock_mgr._create_task.assert_called_once()

    async def test_updates_last_fetch_on_success(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        sub_id = await storage.add_subscription(SUB_URL, "", 3600)
        before = time.time()

        with _http(200, VALID_URI):
            await sm.refresh_subscription(sub_id)

        sub = await storage.get_subscription(sub_id)
        assert sub.last_fetch is not None
        assert sub.last_fetch >= before


# ---------------------------------------------------------------------------
# SubscriptionManager.add_subscription
# ---------------------------------------------------------------------------

class TestAddSubscription:
    async def test_creates_subscription_in_db(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        with _http(200, VALID_URI):
            sub_id, _ = await sm.add_subscription(SUB_URL, "My Sub")
        sub = await storage.get_subscription(sub_id)
        assert sub is not None
        assert sub.name == "My Sub"
        assert sub.url == SUB_URL
        await sm.shutdown()

    async def test_returns_sub_id_and_fetch_result(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        with _http(200, f"{VALID_URI}\n{VALID_URI_2}"):
            sub_id, result = await sm.add_subscription(SUB_URL)
        assert isinstance(sub_id, int)
        assert result.success is True
        assert result.count == 2
        await sm.shutdown()

    async def test_starts_poller_task(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        with _http(200, VALID_URI):
            sub_id, _ = await sm.add_subscription(SUB_URL)
        assert sub_id in sm._tasks
        assert not sm._tasks[sub_id].done()
        await sm.shutdown()

    async def test_fetch_failure_still_adds_subscription(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        with _http(502, ""):
            sub_id, result = await sm.add_subscription(SUB_URL)
        assert result.success is False
        sub = await storage.get_subscription(sub_id)
        assert sub is not None  # subscription exists even if fetch failed
        await sm.shutdown()

    async def test_uses_provided_fetch_interval(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        with _http(200, ""):
            sub_id, _ = await sm.add_subscription(SUB_URL, fetch_interval=7200)
        sub = await storage.get_subscription(sub_id)
        assert sub.fetch_interval == 7200
        await sm.shutdown()


# ---------------------------------------------------------------------------
# SubscriptionManager.add_or_refresh
# ---------------------------------------------------------------------------

class TestAddOrRefresh:
    async def test_new_url_adds_subscription(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        with _http(200, VALID_URI):
            result = await sm.add_or_refresh(SUB_URL)
        assert result.success is True
        subs = await storage.list_subscriptions()
        assert len(subs) == 1
        await sm.shutdown()

    async def test_existing_url_refreshes_without_duplicate(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        with _http(200, VALID_URI):
            await sm.add_or_refresh(SUB_URL)
        with _http(200, f"{VALID_URI}\n{VALID_URI_2}"):
            result = await sm.add_or_refresh(SUB_URL)
        subs = await storage.list_subscriptions()
        assert len(subs) == 1  # no duplicate
        assert result.success is True
        await sm.shutdown()


# ---------------------------------------------------------------------------
# SubscriptionManager.refresh_all
# ---------------------------------------------------------------------------

class TestRefreshAll:
    async def test_empty_returns_empty_list(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        results = await sm.refresh_all()
        assert results == []

    async def test_refreshes_all_subscriptions(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        await storage.add_subscription("https://sub1.example.com", "", 3600)
        await storage.add_subscription("https://sub2.example.com", "", 3600)

        with _http(200, VALID_URI):
            results = await sm.refresh_all()

        assert len(results) == 2
        assert all(r.success for r in results)


# ---------------------------------------------------------------------------
# SubscriptionManager.remove_subscription
# ---------------------------------------------------------------------------

class TestRemoveSubscription:
    async def test_cancels_poller_task(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        with _http(200, ""):
            sub_id, _ = await sm.add_subscription(SUB_URL)

        task = sm._tasks[sub_id]
        await sm.remove_subscription(sub_id)

        assert sub_id not in sm._tasks
        assert task.cancelled() or task.done()

    async def test_marks_proxies_as_dead(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        with _http(200, VALID_URI):
            sub_id, _ = await sm.add_subscription(SUB_URL)

        await sm.remove_subscription(sub_id)

        all_proxies = await storage.get_all_proxies()
        sub_proxies = [p for p in all_proxies if p.subscription_id == sub_id]
        assert all(p.status == "dead" for p in sub_proxies)

    async def test_deletes_subscription_from_db(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        with _http(200, ""):
            sub_id, _ = await sm.add_subscription(SUB_URL)

        await sm.remove_subscription(sub_id)

        sub = await storage.get_subscription(sub_id)
        assert sub is None


# ---------------------------------------------------------------------------
# SubscriptionManager._start_poller (timing and lifecycle)
# ---------------------------------------------------------------------------

class TestStartPoller:
    async def test_task_created_in_tasks_dict(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        sub_id = await storage.add_subscription(SUB_URL, "", 3600)
        sub = await storage.get_subscription(sub_id)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            sm.refresh_subscription = AsyncMock(side_effect=asyncio.CancelledError())
            sm._start_poller(sub)

        assert sub_id in sm._tasks
        try:
            await asyncio.wait_for(sm._tasks[sub_id], timeout=1.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    async def test_sleeps_full_interval_when_never_fetched(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        sub_id = await storage.add_subscription(SUB_URL, "", 3600)
        sub = await storage.get_subscription(sub_id)
        assert sub.last_fetch is None

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            sm.refresh_subscription = AsyncMock(side_effect=asyncio.CancelledError())
            sm._start_poller(sub)
            try:
                await asyncio.wait_for(sm._tasks[sub_id], timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        mock_sleep.assert_called_once_with(3600.0)

    async def test_sleeps_remaining_time_when_recently_fetched(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        sub_id = await storage.add_subscription(SUB_URL, "", 3600)
        sub = await storage.get_subscription(sub_id)
        sub.last_fetch = time.time() - 1800  # fetched 30 min ago

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            sm.refresh_subscription = AsyncMock(side_effect=asyncio.CancelledError())
            sm._start_poller(sub)
            try:
                await asyncio.wait_for(sm._tasks[sub_id], timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        wait = mock_sleep.call_args[0][0]
        assert 1700 <= wait <= 1900  # ~1800s remaining

    async def test_sleeps_zero_when_interval_expired(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        sub_id = await storage.add_subscription(SUB_URL, "", 3600)
        sub = await storage.get_subscription(sub_id)
        sub.last_fetch = time.time() - 7200  # fetched 2 hours ago

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            sm.refresh_subscription = AsyncMock(side_effect=asyncio.CancelledError())
            sm._start_poller(sub)
            try:
                await asyncio.wait_for(sm._tasks[sub_id], timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        assert mock_sleep.call_args[0][0] == 0.0

    async def test_updates_sub_after_each_cycle(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        sub_id = await storage.add_subscription(SUB_URL, "", 3600)
        sub = await storage.get_subscription(sub_id)

        # First call succeeds, second cancels the loop
        fetch_result = FetchResult(url=SUB_URL, success=True, links=[], count=0)
        sm.refresh_subscription = AsyncMock(
            side_effect=[fetch_result, asyncio.CancelledError()]
        )
        # updated sub has different interval
        updated_sub = MagicMock()
        updated_sub.fetch_interval = 7200
        updated_sub.last_fetch = time.time()
        sm._storage.get_subscription = AsyncMock(return_value=updated_sub)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            sm._start_poller(sub)
            try:
                await asyncio.wait_for(sm._tasks[sub_id], timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        assert sub.fetch_interval == 7200

    async def test_shutdown_cancels_all_pollers(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        sub_id1 = await storage.add_subscription("https://sub1.example.com", "", 3600)
        sub_id2 = await storage.add_subscription("https://sub2.example.com", "", 3600)
        sub1 = await storage.get_subscription(sub_id1)
        sub2 = await storage.get_subscription(sub_id2)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            sm._start_poller(sub1)
            sm._start_poller(sub2)

        tasks = list(sm._tasks.values())
        await sm.shutdown()

        assert sm._tasks == {}
        assert all(t.cancelled() or t.done() for t in tasks)
