from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from api.server import create_api
from core.manager import ManagerStatus, ProxyInfo, ProxyManager, UpdateReport
from core.storage import PoolStats, Storage


def _make_pool_stats(**kwargs) -> PoolStats:
    defaults = dict(active=0, dead=0, pending=0, invalid=0, running_processes=0)
    defaults.update(kwargs)
    return PoolStats(**defaults)


def _make_proxy_info(
    proxy_id: int = 1,
    local_port: int = 10800,
    latency_ms: int = 100,
    name: str = "Test",
) -> ProxyInfo:
    return ProxyInfo(
        proxy_id=proxy_id, name=name, host="1.2.3.4",
        port=443, local_port=local_port,
        latency_ms=latency_ms, last_check=1_700_000_000.0,
    )


def _make_manager_status(proxies: list[ProxyInfo] | None = None) -> ManagerStatus:
    return ManagerStatus(
        pool_stats=_make_pool_stats(active=len(proxies or []), running_processes=len(proxies or [])),
        active_proxies=proxies or [],
        check_url="https://www.linkedin.com",
        uptime_seconds=3600.0,
    )


@pytest.fixture
def mock_manager():
    manager = MagicMock(spec=ProxyManager)
    manager.storage = MagicMock(spec=Storage)
    return manager


@pytest.fixture
def app(mock_manager):
    return create_api(mock_manager)


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class TestHealth:
    async def test_returns_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestProxyList:
    async def test_empty_pool(self, client, mock_manager):
        mock_manager.get_status = AsyncMock(return_value=_make_manager_status([]))
        resp = await client.get("/proxy/list")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["proxies"] == []

    async def test_returns_all_active(self, client, mock_manager):
        proxies = [_make_proxy_info(1, 10800, 50, "A"), _make_proxy_info(2, 10801, 80, "B")]
        mock_manager.get_status = AsyncMock(return_value=_make_manager_status(proxies))
        resp = await client.get("/proxy/list")
        data = resp.json()
        assert data["count"] == 2
        ports = {p["port"] for p in data["proxies"]}
        assert ports == {10800, 10801}

    async def test_proxy_url_format(self, client, mock_manager):
        mock_manager.get_status = AsyncMock(
            return_value=_make_manager_status([_make_proxy_info(local_port=10805)])
        )
        resp = await client.get("/proxy/list")
        proxy = resp.json()["proxies"][0]
        assert proxy["proxy_url"] == "socks5://127.0.0.1:10805"
        assert proxy["protocol"] == "socks5"
        assert proxy["host"] == "127.0.0.1"

    async def test_latency_and_name_present(self, client, mock_manager):
        mock_manager.get_status = AsyncMock(
            return_value=_make_manager_status([_make_proxy_info(latency_ms=42, name="Amsterdam")])
        )
        resp = await client.get("/proxy/list")
        proxy = resp.json()["proxies"][0]
        assert proxy["latency_ms"] == 42
        assert proxy["name"] == "Amsterdam"


class TestProxyRandom:
    async def test_returns_proxy_when_available(self, client, mock_manager):
        mock_manager.get_proxy_for_client = AsyncMock(
            return_value=_make_proxy_info(local_port=10803, name="Frankfurt")
        )
        resp = await client.get("/proxy/random")
        assert resp.status_code == 200
        data = resp.json()
        assert data["port"] == 10803
        assert data["name"] == "Frankfurt"

    async def test_503_when_no_proxies(self, client, mock_manager):
        mock_manager.get_proxy_for_client = AsyncMock(return_value=None)
        resp = await client.get("/proxy/random")
        assert resp.status_code == 503
        assert resp.json()["error"] == "no_active_proxies"


class TestProxyBest:
    async def test_returns_lowest_latency(self, client, mock_manager):
        proxies = [
            _make_proxy_info(1, 10800, 200, "Slow"),
            _make_proxy_info(2, 10801, 50, "Fast"),
            _make_proxy_info(3, 10802, 120, "Medium"),
        ]
        mock_manager.get_status = AsyncMock(return_value=_make_manager_status(proxies))
        resp = await client.get("/proxy/best")
        assert resp.status_code == 200
        assert resp.json()["port"] == 10801
        assert resp.json()["name"] == "Fast"

    async def test_503_when_no_proxies(self, client, mock_manager):
        mock_manager.get_status = AsyncMock(return_value=_make_manager_status([]))
        resp = await client.get("/proxy/best")
        assert resp.status_code == 503

    async def test_skips_proxies_without_latency(self, client, mock_manager):
        proxies = [
            ProxyInfo(proxy_id=1, name="No latency", host="1.1.1.1", port=443,
                      local_port=10800, latency_ms=None, last_check=None),
            _make_proxy_info(2, 10801, 75, "With latency"),
        ]
        mock_manager.get_status = AsyncMock(return_value=_make_manager_status(proxies))
        resp = await client.get("/proxy/best")
        assert resp.status_code == 200
        assert resp.json()["port"] == 10801


class TestStatus:
    async def test_status_structure(self, client, mock_manager):
        mock_manager.get_status = AsyncMock(return_value=_make_manager_status([]))
        mock_manager.storage.get_active_proxies = AsyncMock(return_value=[])
        resp = await client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "pool" in data
        assert "check_url" in data
        assert "uptime_seconds" in data
        assert "proxies" in data
        assert data["check_interval_seconds"] == 300

    async def test_pool_stats_in_status(self, client, mock_manager):
        status = ManagerStatus(
            pool_stats=_make_pool_stats(active=3, dead=1, pending=0, invalid=0, running_processes=3),
            active_proxies=[],
            check_url="https://www.linkedin.com",
            uptime_seconds=100.0,
        )
        mock_manager.get_status = AsyncMock(return_value=status)
        mock_manager.storage.get_active_proxies = AsyncMock(return_value=[])
        resp = await client.get("/status")
        pool = resp.json()["pool"]
        assert pool["active"] == 3
        assert pool["dead"] == 1

    async def test_proxy_detail_includes_fail_count(self, client, mock_manager):
        from core.storage import ProcessRow, ProxyRow
        from dataclasses import asdict
        from core.parser import VlessConfig

        config = VlessConfig(
            uuid="9d507afd-7e90-4b7e-8bd8-6877f7a304ae",
            host="1.2.3.4", port=443, raw_uri="vless://...", name="Server",
            security="none", type="tcp", flow="", header_type="none",
            sni="", fp="", alpn="", pbk="", sid="", spx="",
            path="/", host_header="", service_name="",
        )
        proxy_row = ProxyRow(
            id=1, raw_uri="vless://...", host="1.2.3.4", port=443,
            name="Server", security="none", type="tcp", flow="",
            params=asdict(config), status="active",
            last_check=1_700_000_000.0, latency_ms=42, fail_count=2,
        )
        process_row = ProcessRow(
            id=1, proxy_id=1, local_port=10800, pid=1234,
            config_path="/tmp/x.json", status="running",
        )
        mock_manager.get_status = AsyncMock(return_value=_make_manager_status([]))
        mock_manager.storage.get_active_proxies = AsyncMock(return_value=[proxy_row])
        mock_manager.storage.get_process = AsyncMock(return_value=process_row)

        resp = await client.get("/status")
        proxies = resp.json()["proxies"]
        assert len(proxies) == 1
        assert proxies[0]["fail_count"] == 2
        assert proxies[0]["local_port"] == 10800


class TestUpdate:
    VALID_URI = (
        "vless://9d507afd-7e90-4b7e-8bd8-6877f7a304ae@1.2.3.4:443"
        "?security=reality&sni=x.com&pbk=key&sid=sid1"
    )

    async def test_disabled_when_no_secret(self, client, mock_manager):
        with patch("api.server.settings") as s:
            s.API_SECRET_KEY = ""
            s.PROXY_BIND_HOST = "127.0.0.1"
            s.CHECK_INTERVAL = 300
            resp = await client.post(
                "/update",
                json={"links": [self.VALID_URI]},
                headers={"Authorization": "Bearer anything"},
            )
        assert resp.status_code == 404

    async def test_unauthorized_wrong_token(self, client, mock_manager):
        with patch("api.server.settings") as s:
            s.API_SECRET_KEY = "correct-secret"
            s.PROXY_BIND_HOST = "127.0.0.1"
            s.CHECK_INTERVAL = 300
            resp = await client.post(
                "/update",
                json={"links": [self.VALID_URI]},
                headers={"Authorization": "Bearer wrong"},
            )
        assert resp.status_code == 401

    async def test_unauthorized_missing_header(self, client, mock_manager):
        with patch("api.server.settings") as s:
            s.API_SECRET_KEY = "secret"
            s.PROXY_BIND_HOST = "127.0.0.1"
            s.CHECK_INTERVAL = 300
            resp = await client.post("/update", json={"links": [self.VALID_URI]})
        assert resp.status_code == 401

    async def test_authorized_returns_report(self, client, mock_manager):
        mock_manager.update_proxies = AsyncMock(return_value=UpdateReport(
            total_received=1, valid=1, invalid=0,
            parse_errors=[], newly_added=1, already_known=0,
            removed=0, source="api",
        ))
        with patch("api.server.settings") as s:
            s.API_SECRET_KEY = "secret"
            s.PROXY_BIND_HOST = "127.0.0.1"
            s.CHECK_INTERVAL = 300
            resp = await client.post(
                "/update",
                json={"links": [self.VALID_URI]},
                headers={"Authorization": "Bearer secret"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_received"] == 1
        assert data["newly_added"] == 1
        mock_manager.update_proxies.assert_called_once_with([self.VALID_URI], source="api")

    async def test_errors_forwarded(self, client, mock_manager):
        mock_manager.update_proxies = AsyncMock(return_value=UpdateReport(
            total_received=2, valid=1, invalid=1,
            parse_errors=["invalid UUID: 'bad'"],
            newly_added=1, already_known=0, removed=0, source="api",
        ))
        with patch("api.server.settings") as s:
            s.API_SECRET_KEY = "secret"
            s.PROXY_BIND_HOST = "127.0.0.1"
            s.CHECK_INTERVAL = 300
            resp = await client.post(
                "/update",
                json={"links": [self.VALID_URI, "vless://bad"]},
                headers={"Authorization": "Bearer secret"},
            )
        assert resp.json()["errors"] == ["invalid UUID: 'bad'"]
