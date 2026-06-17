import asyncio
import time
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.health import (
    HealthChecker,
    HealthResult,
    check_proxy,
    check_proxy_tcp,
    vless_config_from_proxy,
)
from core.parser import VlessConfig
from core.storage import ProxyRow, Storage


def _make_vless_config(**kwargs) -> VlessConfig:
    defaults = dict(
        uuid="9d507afd-7e90-4b7e-8bd8-6877f7a304ae",
        host="1.2.3.4",
        port=443,
        raw_uri="vless://9d507afd-7e90-4b7e-8bd8-6877f7a304ae@1.2.3.4:443?security=reality&sni=cdn.example.com&pbk=pubkey&sid=shortid",
        name="Test",
        security="reality",
        type="tcp",
        flow="xtls-rprx-vision",
        header_type="none",
        sni="cdn.example.com",
        fp="firefox",
        alpn="",
        pbk="pubkey",
        sid="shortid",
        spx="",
        path="/",
        host_header="",
        service_name="",
    )
    defaults.update(kwargs)
    return VlessConfig(**defaults)


def _make_proxy_row(proxy_id: int = 1, config: VlessConfig | None = None) -> ProxyRow:
    if config is None:
        config = _make_vless_config()
    return ProxyRow(
        id=proxy_id,
        raw_uri=config.raw_uri,
        host=config.host,
        port=config.port,
        name=config.name,
        security=config.security,
        type=config.type,
        flow=config.flow,
        params=asdict(config),
        status="active",
        last_check=None,
        latency_ms=None,
        fail_count=0,
    )


class TestVlessConfigFromProxy:
    def test_roundtrip(self):
        config = _make_vless_config()
        proxy = _make_proxy_row(config=config)
        restored = vless_config_from_proxy(proxy)
        assert restored == config

    def test_all_fields_preserved(self):
        config = _make_vless_config(
            sni="my.sni.com", pbk="mypubkey", sid="mysid",
            flow="xtls-rprx-vision", fp="chrome",
        )
        proxy = _make_proxy_row(config=config)
        restored = vless_config_from_proxy(proxy)
        assert restored.sni == "my.sni.com"
        assert restored.pbk == "mypubkey"
        assert restored.flow == "xtls-rprx-vision"


class TestCheckProxyTcp:
    async def test_reachable_host(self):
        server = await asyncio.start_server(
            lambda r, w: w.close(), "127.0.0.1", 0
        )
        port = server.sockets[0].getsockname()[1]
        async with server:
            result = await check_proxy_tcp("127.0.0.1", port, timeout=2.0)
        assert result is True

    async def test_unreachable_host(self):
        result = await check_proxy_tcp("127.0.0.1", 19799, timeout=1.0)
        assert result is False

    async def test_invalid_host(self):
        result = await check_proxy_tcp("256.256.256.256", 443, timeout=1.0)
        assert result is False


class TestCheckProxy:
    async def test_xray_binary_not_found(self):
        config = _make_vless_config()
        with patch("core.health.settings") as mock_settings:
            mock_settings.XRAY_BINARY = "/nonexistent/xray"
            mock_settings.CHECK_URL = "https://example.com"
            result = await check_proxy(proxy_id=1, vless_config=config)

        assert result.success is False
        assert "not found" in result.error
        assert result.proxy_id == 1
        assert result.status_code is None
        assert result.latency_ms is None

    async def test_result_fields_on_xray_missing(self):
        config = _make_vless_config()
        with patch("core.health.settings") as s, \
             patch("core.health.os.path.exists", return_value=False):
            s.XRAY_BINARY = "/no/xray"
            s.CHECK_URL = "https://linkedin.com"
            result = await check_proxy(42, config)

        assert result.proxy_id == 42
        assert result.check_url == "https://linkedin.com"
        assert isinstance(result.checked_at, float)
        assert result.checked_at <= time.time()


class TestHealthChecker:
    @pytest.fixture
    async def storage(self, tmp_path):
        s = Storage(db_path=str(tmp_path / "test.db"))
        await s.init()
        yield s
        await s.close()

    async def test_check_one_tcp_fail_marks_dead(self, storage):
        config = _make_vless_config(host="127.0.0.1", port=19798)
        await storage.upsert_proxy(config)
        proxy = (await storage.get_all_proxies())[0]

        checker = HealthChecker(storage)
        with patch("core.health.check_proxy_tcp", return_value=False):
            result = await checker.check_one(proxy, config)

        assert result.success is False
        rows = await storage.get_all_proxies()
        assert rows[0].status == "dead"

    async def test_check_one_calls_on_status_change(self, storage):
        config = _make_vless_config(host="127.0.0.1", port=19798)
        await storage.upsert_proxy(config)
        proxy = (await storage.get_all_proxies())[0]

        received: list[HealthResult] = []
        checker = HealthChecker(storage)

        with patch("core.health.check_proxy_tcp", return_value=False):
            await checker.check_one(proxy, config, on_status_change=received.append)

        assert len(received) == 1
        assert isinstance(received[0], HealthResult)

    async def test_check_one_active_on_success(self, storage):
        config = _make_vless_config(host="127.0.0.1", port=19798)
        await storage.upsert_proxy(config)
        proxy = (await storage.get_all_proxies())[0]

        checker = HealthChecker(storage)
        with patch("core.health.check_proxy_tcp", return_value=True), \
             patch("core.health.check_proxy", return_value=HealthResult(
                 proxy_id=proxy.id, success=True, latency_ms=42,
                 status_code=200, error="", checked_at=time.time(),
                 check_url="https://example.com",
             )):
            result = await checker.check_one(proxy, config)

        assert result.success is True
        rows = await storage.get_all_proxies()
        assert rows[0].status == "active"
        assert rows[0].latency_ms == 42

    async def test_check_batch_all_complete(self, storage):
        for i in range(7):
            cfg = _make_vless_config(
                uuid=f"9d507afd-7e90-4b7e-8bd8-{i:012d}",
                host=f"10.0.0.{i + 1}",
                raw_uri=f"vless://9d507afd-7e90-4b7e-8bd8-{i:012d}@10.0.0.{i + 1}:443?security=none",
            )
            await storage.upsert_proxy(cfg)

        proxies = await storage.get_pending_proxies()
        checker = HealthChecker(storage)

        with patch("core.health.check_proxy_tcp", return_value=False):
            results = await checker._check_batch(proxies)

        assert len(results) == 7
        assert all(not r.success for r in results)

    async def test_check_pending_uses_pending_proxies(self, storage):
        config = _make_vless_config()
        await storage.upsert_proxy(config)

        checker = HealthChecker(storage)
        with patch.object(checker, "_check_batch", new_callable=AsyncMock) as mock_batch:
            mock_batch.return_value = []
            await checker.check_pending()
            called_proxies = mock_batch.call_args[0][0]

        assert len(called_proxies) == 1
        assert called_proxies[0].status == "pending"
