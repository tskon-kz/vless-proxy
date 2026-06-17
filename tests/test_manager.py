import asyncio
import time
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.health import HealthResult
from core.manager import ProxyInfo, ProxyManager
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
    for task in list(m._background_tasks):
        task.cancel()
    if m._background_tasks:
        await asyncio.gather(*m._background_tasks, return_exceptions=True)


class TestOnHealthChange:
    async def test_success_starts_process_if_not_running(self, manager, storage):
        config = _make_vless_config()
        proxy_id = await storage.upsert_proxy(config)
        await storage.set_proxy_status(proxy_id, "active")

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

        manager.process_pool._processes[proxy_id] = MagicMock()

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

        manager.process_pool._processes[proxy_id] = MagicMock()

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
        await manager._on_health_change(result)


class TestGetStatus:
    async def test_empty_status(self, manager, storage):
        manager._started_at = time.time() - 10
        status = await manager.get_status()
        assert status.pool_stats.active == 0
        assert status.active_proxies == []
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

        status = await manager.get_status()
        assert status.active_proxies == []
