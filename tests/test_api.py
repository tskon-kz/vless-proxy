from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from api.server import create_api
from config import settings


@pytest.fixture
def mock_manager():
    manager = MagicMock()
    manager.process_pool = MagicMock()
    return manager


@pytest.fixture
def app(mock_manager):
    return create_api(mock_manager)


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class TestProxyBest:
    async def test_returns_best_port(self, client, mock_manager):
        mock_manager.process_pool.get_all_ports.return_value = {1: settings.PROXY_PORT_START, 2: settings.PROXY_PORT_START + 1}
        resp = await client.get("/proxy/best")
        assert resp.status_code == 200
        assert resp.json()["url"] == f"socks5://{settings.PROXY_BIND_HOST}:{settings.PROXY_PORT_START}"

    async def test_fallback_to_lowest_port_when_start_not_running(self, client, mock_manager):
        mock_manager.process_pool.get_all_ports.return_value = {1: 10805}
        resp = await client.get("/proxy/best")
        assert resp.status_code == 200
        assert resp.json()["url"] == f"socks5://{settings.PROXY_BIND_HOST}:10805"

    async def test_503_when_no_proxies(self, client, mock_manager):
        mock_manager.process_pool.get_all_ports.return_value = {}
        resp = await client.get("/proxy/best")
        assert resp.status_code == 503
        assert "error" in resp.json()


class TestProxyList:
    async def test_empty_list(self, client, mock_manager):
        mock_manager.process_pool.get_all_ports.return_value = {}
        resp = await client.get("/proxy/list")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_sorted_socks5_urls(self, client, mock_manager):
        mock_manager.process_pool.get_all_ports.return_value = {2: 10801, 1: 10800}
        resp = await client.get("/proxy/list")
        urls = resp.json()
        assert urls == [
            f"socks5://{settings.PROXY_BIND_HOST}:10800",
            f"socks5://{settings.PROXY_BIND_HOST}:10801",
        ]

    async def test_url_format(self, client, mock_manager):
        mock_manager.process_pool.get_all_ports.return_value = {1: 10800}
        resp = await client.get("/proxy/list")
        assert resp.json()[0].startswith("socks5://")
