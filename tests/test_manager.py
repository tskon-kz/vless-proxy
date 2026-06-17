import asyncio
import time
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.health import HealthResult
from core.manager import ProxyInfo, ProxyManager, UpdateReport
from core.parser import VlessConfig
from core.storage import ProcessRow, ProxyRow, Storage


def _make_vless_config(
    host: str = "1.2.3.4",
    uuid: str = "9d507afd-7e90-4b7e-8bd8-6877f7a304ae",
    port: int = 443,
) -> VlessConfig:
    raw_uri = f"vless://{uuid}@{host}:{port}?security=none"
    return VlessConfig(
        uuid=uuid, host=host, port=port,
        raw_uri=raw_uri, name="Test", security="none",
        type="tcp", flow="", header_type="none",
        sni="", fp="", alpn="", pbk="", sid="", spx="",
        path="/", host_header="", service_name="",
    )


def _make_proxy_row(proxy_id: int = 1, config: VlessConfig | None = None, status: str = "active") -> ProxyRow:
    if config is None:
        config = _make_vless_config()
    return ProxyRow(
        id=proxy_id, raw_uri=config.raw_uri, host=config.host,
        port=config.port, name=config.name, security=config.security,
        type=config.type, flow=config.flow, params=asdict(config),
        status=status, last_check=None, latency_ms=50, fail_count=0,
    )


def _make_process_row(proxy_id: int = 1, local_port: int = 10800, status: str = "running") -> ProcessRow:
    return ProcessRow(
        id=1, proxy_id=proxy_id, local_port=local_port,
        pid=1234, config_path="/tmp/x.json", status=status,
    )


@pytest.fixture
async def storage(tmp_path):
    s = Storage(db_path=str(tmp_path / "test.db"))
    await s.init()
    yield s
    await s.close()


@pytest.fixture
async def manager(storage):
    m = ProxyManager(storage)
    yield m
    # Cancel any background tasks before storage closes
    for task in list(m._background_tasks):
        task.cancel()
    if m._background_tasks:
        await asyncio.gather(*m._background_tasks, return_exceptions=True)


class TestUpdateProxies:
    VALID_URI = (
        "vless://9d507afd-7e90-4b7e-8bd8-6877f7a304ae@1.2.3.4:443"
        "?security=reality&sni=x.com&pbk=pubkey&sid=sid1"
    )
    VALID_URI_2 = (
        "vless://aaaaaaaa-7e90-4b7e-8bd8-6877f7a304ae@2.2.2.2:443"
        "?security=reality&sni=y.com&pbk=pubkey2&sid=sid2"
    )

    async def test_valid_links_added(self, manager):
        report = await manager.update_proxies([self.VALID_URI], source="test")
        assert report.valid == 1
        assert report.invalid == 0
        assert report.newly_added == 1
        assert report.total_received == 1

    async def test_invalid_links_counted(self, manager):
        bad_vless = "vless://not-a-uuid@1.2.3.4:443?security=none"
        report = await manager.update_proxies(
            [self.VALID_URI, bad_vless, "not-a-link-at-all"], source="test"
        )
        assert report.total_received == 3
        assert report.valid == 1
        assert report.invalid == 2
        # parse_errors only covers attempted-but-failed vless URIs
        assert len(report.parse_errors) == 1
        assert "UUID" in report.parse_errors[0]

    async def test_already_known_not_counted_as_new(self, manager):
        await manager.update_proxies([self.VALID_URI], source="test")
        report = await manager.update_proxies([self.VALID_URI], source="test")
        assert report.newly_added == 0
        assert report.already_known == 1

    async def test_removed_proxies_counted(self, manager):
        await manager.update_proxies([self.VALID_URI, self.VALID_URI_2], source="test")
        report = await manager.update_proxies([self.VALID_URI], source="test")
        assert report.removed == 1

    async def test_source_stored(self, manager):
        report = await manager.update_proxies([self.VALID_URI], source="telegram")
        assert report.source == "telegram"

    async def test_lock_prevents_concurrent_updates(self, manager):
        results = []

        async def run():
            r = await manager.update_proxies([self.VALID_URI], source="test")
            results.append(r)

        await asyncio.gather(run(), run())
        assert len(results) == 2

    async def test_stops_process_for_removed_proxy(self, manager, storage):
        from core.parser import parse_vless
        from core.xray import XrayProcess

        # Insert both proxies directly so no background health task is created
        config_a = parse_vless(self.VALID_URI).config
        config_b = parse_vless(self.VALID_URI_2).config
        id_a = await storage.upsert_proxy(config_a)
        id_b = await storage.upsert_proxy(config_b)

        for proxy_id in (id_a, id_b):
            await storage.set_proxy_status(proxy_id, "active")
            await storage.upsert_process(proxy_id, 10800 + proxy_id, f"/tmp/{proxy_id}.json")
            await storage.set_process_pid(proxy_id, 10800 + proxy_id, 1000 + proxy_id, "running")
            proc = XrayProcess(proxy_id, 10800 + proxy_id, f"/tmp/{proxy_id}.json", storage)
            proc._proc = MagicMock()
            proc._proc.returncode = None
            proc._proc.send_signal = MagicMock()
            proc._proc.wait = AsyncMock(return_value=0)
            proc._pid = 1000 + proxy_id
            manager.process_pool._processes[proxy_id] = proc

        # Suppress background health tasks for this test
        with patch.object(manager, "_create_task", return_value=MagicMock()), \
             patch("core.xray.os.path.exists", return_value=True), \
             patch("core.xray.os.remove"):
            report = await manager.update_proxies([self.VALID_URI], source="test")

        assert report.removed == 1
        assert manager.process_pool.get_process(id_b) is None
        assert manager.process_pool.get_process(id_a) is not None


class TestOnHealthChange:
    async def test_success_starts_process_if_not_running(self, manager, storage):
        config = _make_vless_config()
        proxy_id = await storage.upsert_proxy(config)
        await storage.set_proxy_status(proxy_id, "active")
        proxy = await storage.get_proxy_by_id(proxy_id)

        result = HealthResult(
            proxy_id=proxy_id, success=True, latency_ms=30,
            status_code=200, error="", checked_at=time.time(),
            check_url="https://example.com",
        )

        with patch.object(manager.process_pool, "start_proxy", new_callable=AsyncMock) as mock_start:
            mock_start.return_value = MagicMock()
            await manager._on_health_change(result)
            mock_start.assert_called_once()

    async def test_success_does_not_restart_running_process(self, manager, storage):
        config = _make_vless_config()
        proxy_id = await storage.upsert_proxy(config)
        await storage.set_proxy_status(proxy_id, "active")

        # Simulate already-running process in pool
        fake_proc = MagicMock()
        manager.process_pool._processes[proxy_id] = fake_proc

        result = HealthResult(
            proxy_id=proxy_id, success=True, latency_ms=30,
            status_code=200, error="", checked_at=time.time(),
            check_url="https://example.com",
        )

        with patch.object(manager.process_pool, "start_proxy", new_callable=AsyncMock) as mock_start:
            await manager._on_health_change(result)
            mock_start.assert_not_called()

        manager.process_pool._processes.clear()

    async def test_failure_stops_running_process(self, manager, storage):
        config = _make_vless_config()
        proxy_id = await storage.upsert_proxy(config)

        fake_proc = MagicMock()
        manager.process_pool._processes[proxy_id] = fake_proc

        result = HealthResult(
            proxy_id=proxy_id, success=False, latency_ms=None,
            status_code=None, error="timeout", checked_at=time.time(),
            check_url="https://example.com",
        )

        with patch.object(manager.process_pool, "stop_proxy", new_callable=AsyncMock) as mock_stop:
            await manager._on_health_change(result)
            mock_stop.assert_called_once_with(proxy_id)

        manager.process_pool._processes.clear()

    async def test_failure_noop_if_no_process(self, manager, storage):
        config = _make_vless_config()
        proxy_id = await storage.upsert_proxy(config)

        result = HealthResult(
            proxy_id=proxy_id, success=False, latency_ms=None,
            status_code=None, error="timeout", checked_at=time.time(),
            check_url="https://example.com",
        )

        with patch.object(manager.process_pool, "stop_proxy", new_callable=AsyncMock) as mock_stop:
            await manager._on_health_change(result)
            mock_stop.assert_not_called()

    async def test_unknown_proxy_id_is_ignored(self, manager):
        result = HealthResult(
            proxy_id=9999, success=True, latency_ms=10,
            status_code=200, error="", checked_at=time.time(),
            check_url="https://example.com",
        )
        await manager._on_health_change(result)  # should not raise


class TestGetStatus:
    async def test_empty_status(self, manager, storage):
        manager._started_at = time.time() - 10
        status = await manager.get_status()
        assert status.pool_stats.active == 0
        assert status.active_proxies == []
        assert status.check_url == "https://www.linkedin.com"
        assert status.uptime_seconds >= 10

    async def test_active_proxy_with_running_process(self, manager, storage):
        config = _make_vless_config()
        proxy_id = await storage.upsert_proxy(config)
        await storage.set_proxy_status(proxy_id, "active", latency_ms=42)
        await storage.upsert_process(proxy_id, 10800, "/tmp/x.json")
        await storage.set_process_pid(proxy_id, 10800, 1234, "running")

        status = await manager.get_status()
        assert len(status.active_proxies) == 1
        info = status.active_proxies[0]
        assert info.local_port == 10800
        assert info.latency_ms == 42

    async def test_active_proxy_without_running_process_excluded(self, manager, storage):
        config = _make_vless_config()
        proxy_id = await storage.upsert_proxy(config)
        await storage.set_proxy_status(proxy_id, "active")
        # No process record → not included

        status = await manager.get_status()
        assert status.active_proxies == []


class TestGetProxyForClient:
    async def test_returns_none_when_no_active(self, manager):
        result = await manager.get_proxy_for_client()
        assert result is None

    async def test_returns_proxy_info_when_running(self, manager, storage):
        config = _make_vless_config()
        proxy_id = await storage.upsert_proxy(config)
        await storage.set_proxy_status(proxy_id, "active")
        await storage.upsert_process(proxy_id, 10800, "/tmp/x.json")
        await storage.set_process_pid(proxy_id, 10800, 1234, "running")

        result = await manager.get_proxy_for_client()
        assert isinstance(result, ProxyInfo)
        assert result.local_port == 10800

    async def test_returns_none_when_process_not_running(self, manager, storage):
        config = _make_vless_config()
        proxy_id = await storage.upsert_proxy(config)
        await storage.set_proxy_status(proxy_id, "active")
        await storage.upsert_process(proxy_id, 10800, "/tmp/x.json")
        await storage.set_process_pid(proxy_id, 10800, None, "stopped")

        result = await manager.get_proxy_for_client()
        assert result is None
