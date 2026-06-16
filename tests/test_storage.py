import pytest

from core.parser import VlessConfig
from core.storage import PoolStats, Storage, UpdateStats


def _make_config(
    uuid: str = "9d507afd-7e90-4b7e-8bd8-6877f7a304ae",
    host: str = "1.1.1.1",
    port: int = 443,
    name: str = "Test",
    raw_uri: str | None = None,
) -> VlessConfig:
    if raw_uri is None:
        raw_uri = f"vless://{uuid}@{host}:{port}?security=none#{name}"
    return VlessConfig(
        uuid=uuid,
        host=host,
        port=port,
        raw_uri=raw_uri,
        name=name,
        security="none",
    )


@pytest.fixture
async def storage(tmp_path):
    s = Storage(db_path=str(tmp_path / "test.db"))
    await s.init()
    yield s
    await s.close()


@pytest.fixture
def config_a():
    return _make_config(host="1.1.1.1", name="Server A")


@pytest.fixture
def config_b():
    return _make_config(
        uuid="aaaaaaaa-7e90-4b7e-8bd8-6877f7a304ae",
        host="2.2.2.2",
        name="Server B",
    )


class TestUpsertProxy:
    async def test_insert_returns_id(self, storage, config_a):
        proxy_id = await storage.upsert_proxy(config_a)
        assert isinstance(proxy_id, int)
        assert proxy_id > 0

    async def test_new_proxy_status_pending(self, storage, config_a):
        await storage.upsert_proxy(config_a)
        rows = await storage.get_pending_proxies()
        assert len(rows) == 1
        assert rows[0].status == "pending"

    async def test_upsert_same_uri_returns_same_id(self, storage, config_a):
        id1 = await storage.upsert_proxy(config_a)
        id2 = await storage.upsert_proxy(config_a)
        assert id1 == id2

    async def test_upsert_does_not_change_status(self, storage, config_a):
        proxy_id = await storage.upsert_proxy(config_a)
        await storage.set_proxy_status(proxy_id, "active")
        await storage.upsert_proxy(config_a)
        rows = await storage.get_active_proxies()
        assert len(rows) == 1


class TestSetProxyStatus:
    async def test_set_active_resets_fail_count(self, storage, config_a):
        proxy_id = await storage.upsert_proxy(config_a)
        await storage.set_proxy_status(proxy_id, "dead")
        await storage.set_proxy_status(proxy_id, "dead")
        await storage.set_proxy_status(proxy_id, "active", latency_ms=50)

        rows = await storage.get_active_proxies()
        assert rows[0].fail_count == 0
        assert rows[0].latency_ms == 50

    async def test_set_dead_increments_fail_count(self, storage, config_a):
        proxy_id = await storage.upsert_proxy(config_a)
        await storage.set_proxy_status(proxy_id, "dead")
        await storage.set_proxy_status(proxy_id, "dead")

        rows = await storage.get_all_proxies()
        assert rows[0].fail_count == 2

    async def test_set_active_clears_latency(self, storage, config_a):
        proxy_id = await storage.upsert_proxy(config_a)
        await storage.set_proxy_status(proxy_id, "active", latency_ms=123)
        rows = await storage.get_active_proxies()
        assert rows[0].latency_ms == 123


class TestGetProxies:
    async def test_get_active_returns_only_active(self, storage, config_a, config_b):
        id_a = await storage.upsert_proxy(config_a)
        await storage.upsert_proxy(config_b)
        await storage.set_proxy_status(id_a, "active")

        active = await storage.get_active_proxies()
        pending = await storage.get_pending_proxies()
        assert len(active) == 1
        assert active[0].host == "1.1.1.1"
        assert len(pending) == 1

    async def test_get_all_returns_everything(self, storage, config_a, config_b):
        await storage.upsert_proxy(config_a)
        await storage.upsert_proxy(config_b)
        rows = await storage.get_all_proxies()
        assert len(rows) == 2


class TestReplaceAll:
    async def test_adds_new_proxies(self, storage, config_a, config_b):
        stats = await storage.replace_all([config_a, config_b], source="test")
        assert stats.added == 2
        assert stats.removed == 0

    async def test_removes_missing_proxies(self, storage, config_a, config_b):
        await storage.replace_all([config_a, config_b], source="test")
        stats = await storage.replace_all([config_a], source="test")
        assert stats.removed == 1

        all_rows = await storage.get_all_proxies()
        dead = [r for r in all_rows if r.status == "dead"]
        assert len(dead) == 1
        assert dead[0].host == "2.2.2.2"

    async def test_removed_proxies_not_deleted(self, storage, config_a, config_b):
        await storage.replace_all([config_a, config_b], source="test")
        await storage.replace_all([config_a], source="test")
        all_rows = await storage.get_all_proxies()
        assert len(all_rows) == 2

    async def test_existing_proxy_not_counted_as_added(self, storage, config_a):
        await storage.replace_all([config_a], source="test")
        stats = await storage.replace_all([config_a], source="test")
        assert stats.added == 0

    async def test_rollback_on_failure(self, storage, config_a):
        await storage.upsert_proxy(config_a)
        original_rows = await storage.get_all_proxies()

        bad_config = _make_config(host="3.3.3.3", raw_uri="")
        bad_config.raw_uri = None  # will cause DB constraint failure

        try:
            await storage.replace_all([bad_config], source="test")
        except Exception:
            pass

        rows_after = await storage.get_all_proxies()
        assert len(rows_after) == len(original_rows)


class TestProcesses:
    async def test_upsert_and_get_process(self, storage, config_a):
        proxy_id = await storage.upsert_proxy(config_a)
        await storage.upsert_process(proxy_id, local_port=10800, config_path="/tmp/x.json")

        proc = await storage.get_process(proxy_id)
        assert proc is not None
        assert proc.local_port == 10800
        assert proc.config_path == "/tmp/x.json"
        assert proc.status == "stopped"

    async def test_set_process_pid(self, storage, config_a):
        proxy_id = await storage.upsert_proxy(config_a)
        await storage.upsert_process(proxy_id, local_port=10800, config_path="/tmp/x.json")
        await storage.set_process_pid(proxy_id, pid=1234, status="running")

        proc = await storage.get_process(proxy_id)
        assert proc.pid == 1234
        assert proc.status == "running"

    async def test_get_process_none_if_not_exists(self, storage, config_a):
        proxy_id = await storage.upsert_proxy(config_a)
        proc = await storage.get_process(proxy_id)
        assert proc is None

    async def test_get_available_port(self, storage, config_a, config_b):
        id_a = await storage.upsert_proxy(config_a)
        id_b = await storage.upsert_proxy(config_b)
        await storage.upsert_process(id_a, local_port=10800, config_path="/tmp/a.json")
        await storage.upsert_process(id_b, local_port=10801, config_path="/tmp/b.json")
        await storage.set_process_pid(id_a, pid=100, status="running")
        await storage.set_process_pid(id_b, pid=101, status="running")

        port = await storage.get_available_port()
        assert port == 10802

    async def test_get_available_port_none_when_full(self, storage):
        from config import settings
        configs = []
        for i, port in enumerate(range(settings.PROXY_PORT_START, settings.PROXY_PORT_END + 1)):
            cfg = _make_config(
                uuid=f"9d507afd-7e90-4b7e-8bd8-{i:012d}",
                host=f"10.0.0.{i + 1}",
                port=port,
                raw_uri=f"vless://9d507afd-7e90-4b7e-8bd8-{i:012d}@10.0.0.{i + 1}:{port}?security=none",
            )
            configs.append(cfg)
            proxy_id = await storage.upsert_proxy(cfg)
            await storage.upsert_process(proxy_id, local_port=port, config_path=f"/tmp/{i}.json")
            await storage.set_process_pid(proxy_id, pid=1000 + i, status="running")

        port = await storage.get_available_port()
        assert port is None


class TestGetStats:
    async def test_stats_counts(self, storage, config_a, config_b):
        id_a = await storage.upsert_proxy(config_a)
        id_b = await storage.upsert_proxy(config_b)
        await storage.set_proxy_status(id_a, "active")
        await storage.set_proxy_status(id_b, "dead")

        stats = await storage.get_stats()
        assert stats.active == 1
        assert stats.dead == 1
        assert stats.pending == 0

    async def test_stats_running_processes(self, storage, config_a):
        proxy_id = await storage.upsert_proxy(config_a)
        await storage.set_proxy_status(proxy_id, "active")
        await storage.upsert_process(proxy_id, local_port=10800, config_path="/tmp/x.json")
        await storage.set_process_pid(proxy_id, pid=999, status="running")

        stats = await storage.get_stats()
        assert stats.running_processes == 1

    async def test_empty_db_stats(self, storage):
        stats = await storage.get_stats()
        assert stats == PoolStats(active=0, dead=0, pending=0, invalid=0, running_processes=0)
