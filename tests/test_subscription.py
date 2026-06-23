import asyncio
import base64
import os
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.subscription import (
    FetchResult,
    SubscriptionManager,
    _decode_body,
    _fetch_subscription,
)

VALID_URI = (
    "vless://9d507afd-7e90-4b7e-8bd8-6877f7a304ae@1.2.3.4:443"
    "?security=tls&type=tcp#Server1"
)
VALID_URI_2 = (
    "vless://aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee@5.6.7.8:443"
    "?security=tls&type=tcp#Server2"
)
SUB_URL = "https://sub.example.com/token"


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
    mgr.process_pool.get_process = MagicMock(return_value=None)
    return mgr


def _http(status: int = 200, body: str = "") -> patch:
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
        result = _decode_body(encoded)
        assert "vless://" in result
        assert result == content

    def test_plain_text_returned_as_is(self):
        plain = f"{VALID_URI}\n{VALID_URI_2}"
        result = _decode_body(plain)
        assert result == plain

    def test_base64_without_vless_returns_plain(self):
        content = "not a vless link at all"
        encoded = base64.b64encode(content.encode()).decode()
        result = _decode_body(encoded)
        assert result == encoded

    def test_invalid_base64_returns_plain(self):
        garbage = "!!!not_base64!!!"
        result = _decode_body(garbage)
        assert result == garbage

    def test_base64_with_newlines_stripped_before_decode(self):
        content = VALID_URI
        encoded = base64.b64encode(content.encode()).decode()
        wrapped = "\n".join(encoded[i:i+60] for i in range(0, len(encoded), 60))
        result = _decode_body(wrapped)
        assert "vless://" in result


# ---------------------------------------------------------------------------
# SubscriptionFetcher.fetch — returns (list[str], error_str)
# ---------------------------------------------------------------------------

class TestFetch:
    async def test_returns_links_from_plain_text(self):
        body = f"{VALID_URI}\n{VALID_URI_2}\nnot-a-link"
        with _http(200, body):
            links, error = await _fetch_subscription(SUB_URL)
        assert not error
        assert len(links) == 2
        assert all(l.startswith("vless://") for l in links)

    async def test_returns_links_from_base64(self):
        content = f"{VALID_URI}\n{VALID_URI_2}"
        encoded = base64.b64encode(content.encode()).decode()
        with _http(200, encoded):
            links, error = await _fetch_subscription(SUB_URL)
        assert not error
        assert len(links) == 2

    async def test_non_200_returns_error(self):
        with _http(404, ""):
            links, error = await _fetch_subscription(SUB_URL)
        assert "404" in error
        assert links == []

    async def test_timeout_returns_error(self):
        with patch("core.subscription.settings") as s:
            s.SUBSCRIPTION_TIMEOUT = 30
            with _http_raise(asyncio.TimeoutError()):
                links, error = await _fetch_subscription(SUB_URL)
        assert "timeout" in error.lower()
        assert links == []

    async def test_connection_error_returns_error(self):
        with _http_raise(OSError("connection refused")):
            links, error = await _fetch_subscription(SUB_URL)
        assert error != ""
        assert links == []

    async def test_empty_response_returns_zero_links(self):
        with _http(200, "# just comments\nhello world"):
            links, error = await _fetch_subscription(SUB_URL)
        assert not error
        assert links == []


# ---------------------------------------------------------------------------
# SubscriptionManager.refresh
# ---------------------------------------------------------------------------

class TestRefresh:
    async def test_sub_not_found_returns_error(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        result = await sm.refresh(9999)
        assert result.success is False
        assert "not found" in result.error

    async def test_fetch_failure_increments_fail_count(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        sub_id = await storage.add_subscription(SUB_URL, "", 3600)

        with _http(503, ""):
            await sm.refresh(sub_id)

        sub = await storage.get_subscription(sub_id)
        assert sub.fail_count == 1
        assert sub.last_fetch is None

    async def test_fetch_success_no_links_updates_db(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        sub_id = await storage.add_subscription(SUB_URL, "", 3600)

        with _http(200, "no vless links here"):
            await sm.refresh(sub_id)

        sub = await storage.get_subscription(sub_id)
        assert sub.fail_count == 0
        assert sub.last_fetch is not None

    async def test_fetch_success_replaces_subscription_proxies(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        sub_id = await storage.add_subscription(SUB_URL, "", 3600)

        body = f"{VALID_URI}\n{VALID_URI_2}"
        with _http(200, body):
            result = await sm.refresh(sub_id)

        assert result.success is True
        sub_proxies = [p for p in await storage.get_all_proxies() if p.subscription_id == sub_id]
        assert len(sub_proxies) == 2

    async def test_fetch_success_kicks_health_check(self, storage):
        mock_mgr = _mock_manager()
        sm = SubscriptionManager(storage, mock_mgr)
        sub_id = await storage.add_subscription(SUB_URL, "", 3600)

        with _http(200, VALID_URI):
            await sm.refresh(sub_id)

        mock_mgr._create_task.assert_called_once()

    async def test_updates_last_fetch_on_success(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        sub_id = await storage.add_subscription(SUB_URL, "", 3600)
        before = time.time()

        with _http(200, VALID_URI):
            await sm.refresh(sub_id)

        sub = await storage.get_subscription(sub_id)
        assert sub.last_fetch is not None
        assert sub.last_fetch >= before


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
# SubscriptionManager._start_poller
# ---------------------------------------------------------------------------

class TestStartPoller:
    async def test_task_created_in_tasks_dict(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        sub_id = await storage.add_subscription(SUB_URL, "", 3600)
        sub = await storage.get_subscription(sub_id)

        sm.refresh = AsyncMock(side_effect=asyncio.CancelledError())
        with patch("asyncio.sleep", new_callable=AsyncMock):
            sm._start_poller(sub)

        assert sub_id in sm._tasks
        try:
            await asyncio.wait_for(sm._tasks[sub_id], timeout=1.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    async def test_fetches_immediately_when_never_fetched(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        sub_id = await storage.add_subscription(SUB_URL, "", 3600)
        sub = await storage.get_subscription(sub_id)
        assert sub.last_fetch is None

        sm.refresh = AsyncMock(side_effect=asyncio.CancelledError())
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            sm._start_poller(sub)
            try:
                await asyncio.wait_for(sm._tasks[sub_id], timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        # No initial sleep when never fetched
        mock_sleep.assert_not_called()
        sm.refresh.assert_called_once()

    async def test_sleeps_remaining_time_when_recently_fetched(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        sub_id = await storage.add_subscription(SUB_URL, "", 3600)
        sub = await storage.get_subscription(sub_id)
        sub.last_fetch = time.time() - 1800  # fetched 30 min ago

        sm.refresh = AsyncMock(side_effect=asyncio.CancelledError())
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
             patch("core.subscription.settings") as s:
            s.SUBSCRIPTION_FETCH_INTERVAL = 3600
            sm._start_poller(sub)
            try:
                await asyncio.wait_for(sm._tasks[sub_id], timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        wait = mock_sleep.call_args[0][0]
        assert 1700 <= wait <= 1900

    async def test_no_sleep_when_interval_expired(self, storage):
        sm = SubscriptionManager(storage, _mock_manager())
        sub_id = await storage.add_subscription(SUB_URL, "", 3600)
        sub = await storage.get_subscription(sub_id)
        sub.last_fetch = time.time() - 7200  # 2 hours ago

        sm.refresh = AsyncMock(side_effect=asyncio.CancelledError())
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
             patch("core.subscription.settings") as s:
            s.SUBSCRIPTION_FETCH_INTERVAL = 3600
            sm._start_poller(sub)
            try:
                await asyncio.wait_for(sm._tasks[sub_id], timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        mock_sleep.assert_not_called()

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
