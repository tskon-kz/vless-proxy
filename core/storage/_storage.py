import json
import time
from dataclasses import asdict

import aiosqlite

from config import settings
from core.parser import VlessConfig
from core.storage._ddl import CREATE_DOWNTIME_EVENTS, CREATE_PROCESSES, CREATE_PROXIES, CREATE_SUBSCRIPTIONS
from core.storage._models import (
    DownStat,
    PoolStats,
    ProcessRow,
    ProxyRow,
    SubscriptionRow,
    _row_to_downstat,
    _row_to_process,
    _row_to_proxy,
    _row_to_subscription,
)


class Storage:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or settings.DB_PATH
        self._db: aiosqlite.Connection | None = None

    @property
    def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Storage.init() has not been called")
        return self._db

    async def init(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.execute(CREATE_PROXIES)
        await self._db.execute(CREATE_PROCESSES)
        await self._db.execute(CREATE_SUBSCRIPTIONS)
        await self._db.execute(CREATE_DOWNTIME_EVENTS)

        try:
            await self._db.execute("ALTER TABLE proxies ADD COLUMN subscription_id INTEGER")
        except Exception:
            pass

        # Wipe proxy state on every restart so stale data never accumulates.
        # Subscription pollers re-fetch immediately because last_fetch is reset.
        await self._db.execute("DELETE FROM proxies")
        await self._db.execute("UPDATE subscriptions SET last_fetch = NULL")
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def _fetchone(self, sql: str, params: tuple = ()) -> aiosqlite.Row | None:
        async with self._conn.execute(sql, params) as cursor:
            return await cursor.fetchone()

    # -- proxies --

    async def upsert_proxy(self, config: VlessConfig) -> int:
        now = time.time()
        row = await self._fetchone(
            """
            INSERT INTO proxies
                (raw_uri, uuid, host, port, name, security, type, flow,
                 params_json, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            ON CONFLICT(raw_uri) DO UPDATE SET
                uuid        = excluded.uuid,
                host        = excluded.host,
                port        = excluded.port,
                name        = excluded.name,
                security    = excluded.security,
                type        = excluded.type,
                flow        = excluded.flow,
                params_json = excluded.params_json,
                updated_at  = excluded.updated_at
            RETURNING id
            """,
            (
                config.raw_uri, config.uuid, config.host, config.port,
                config.name, config.security, config.type, config.flow,
                json.dumps(asdict(config)), now, now,
            ),
        )
        await self._conn.commit()
        return row["id"]

    async def set_proxy_status(self, proxy_id: int, status: str, latency_ms: int | None = None) -> None:
        now = time.time()
        if status == "active":
            await self._conn.execute(
                "UPDATE proxies SET status=?, last_check=?, latency_ms=?, fail_count=0, updated_at=? WHERE id=?",
                (status, now, latency_ms, now, proxy_id),
            )
        elif status == "dead":
            await self._conn.execute(
                "UPDATE proxies SET status=?, last_check=?, latency_ms=NULL, fail_count=fail_count+1, updated_at=? WHERE id=?",
                (status, now, now, proxy_id),
            )
        else:
            await self._conn.execute(
                "UPDATE proxies SET status=?, last_check=?, latency_ms=?, updated_at=? WHERE id=?",
                (status, now, latency_ms, now, proxy_id),
            )
        await self._conn.commit()

    async def _fetch_proxies(self, status: str | None = None) -> list[ProxyRow]:
        if status:
            sql, params = "SELECT * FROM proxies WHERE status = ?", (status,)
        else:
            sql, params = "SELECT * FROM proxies", ()
        async with self._conn.execute(sql, params) as cursor:
            return [_row_to_proxy(r) async for r in cursor]

    async def get_active_proxies(self) -> list[ProxyRow]:
        return await self._fetch_proxies("active")

    async def get_pending_proxies(self) -> list[ProxyRow]:
        return await self._fetch_proxies("pending")

    async def get_dead_proxies(self) -> list[ProxyRow]:
        return await self._fetch_proxies("dead")

    async def get_all_proxies(self) -> list[ProxyRow]:
        return await self._fetch_proxies()

    async def get_proxy_by_id(self, proxy_id: int) -> ProxyRow | None:
        row = await self._fetchone("SELECT * FROM proxies WHERE id = ?", (proxy_id,))
        return _row_to_proxy(row) if row else None

    # -- processes --

    async def upsert_process(self, proxy_id: int, local_port: int, config_path: str) -> None:
        await self._conn.execute(
            "DELETE FROM processes WHERE proxy_id = ? AND local_port != ?",
            (proxy_id, local_port),
        )
        await self._conn.execute(
            """
            INSERT INTO processes (proxy_id, local_port, config_path, status)
            VALUES (?, ?, ?, 'stopped')
            ON CONFLICT(local_port) DO UPDATE SET
                proxy_id    = excluded.proxy_id,
                config_path = excluded.config_path,
                status      = 'stopped',
                pid         = NULL
            """,
            (proxy_id, local_port, config_path),
        )
        await self._conn.commit()

    async def set_process_pid(self, proxy_id: int, local_port: int, pid: int | None, status: str) -> None:
        now = time.time()
        await self._conn.execute(
            "UPDATE processes SET pid=?, status=?, started_at=? WHERE proxy_id=? AND local_port=?",
            (pid, status, now if pid is not None else None, proxy_id, local_port),
        )
        await self._conn.commit()

    async def get_process(self, proxy_id: int) -> ProcessRow | None:
        row = await self._fetchone("SELECT * FROM processes WHERE proxy_id = ?", (proxy_id,))
        return _row_to_process(row) if row else None

    async def get_available_port(self) -> int | None:
        async with self._conn.execute(
            "SELECT local_port FROM processes WHERE status = 'running'"
        ) as cursor:
            used = {r["local_port"] async for r in cursor}
        for port in range(settings.PROXY_PORT_START, settings.PROXY_PORT_END + 1):
            if port not in used:
                return port
        return None

    # -- stats --

    async def get_stats(self) -> PoolStats:
        row = await self._fetchone(
            """
            SELECT
                SUM(status = 'active')  AS active,
                SUM(status = 'dead')    AS dead,
                SUM(status = 'pending') AS pending
            FROM proxies
            """
        )
        proc_row = await self._fetchone(
            "SELECT COUNT(*) AS cnt FROM processes WHERE status = 'running'"
        )
        return PoolStats(
            active=row["active"] or 0,
            dead=row["dead"] or 0,
            pending=row["pending"] or 0,
            running_processes=proc_row["cnt"] or 0,
        )

    # -- downtime --

    async def record_down(self, proxy_name: str, proxy_host: str) -> None:
        now = time.time()
        await self._conn.execute(
            """
            INSERT INTO downtime_events (proxy_name, proxy_host, went_down_at)
            SELECT ?, ?, ?
            WHERE NOT EXISTS (
                SELECT 1 FROM downtime_events WHERE proxy_name = ? AND came_up_at IS NULL
            )
            """,
            (proxy_name, proxy_host, now, proxy_name),
        )
        await self._conn.commit()

    async def record_up(self, proxy_name: str) -> None:
        now = time.time()
        await self._conn.execute(
            """
            UPDATE downtime_events SET came_up_at = ?
            WHERE id = (
                SELECT id FROM downtime_events
                WHERE proxy_name = ? AND came_up_at IS NULL
                ORDER BY went_down_at DESC
                LIMIT 1
            )
            """,
            (now, proxy_name),
        )
        await self._conn.commit()

    async def get_down_stats(self, since_ts: float) -> list[DownStat]:
        now = time.time()
        async with self._conn.execute(
            """
            SELECT
                proxy_name,
                proxy_host,
                COUNT(*) AS down_count,
                SUM(COALESCE(came_up_at, ?) - went_down_at) AS total_downtime_s
            FROM downtime_events
            WHERE went_down_at > ?
            GROUP BY proxy_name, proxy_host
            ORDER BY down_count DESC, total_downtime_s DESC
            """,
            (now, since_ts),
        ) as cursor:
            return [_row_to_downstat(r) async for r in cursor]

    # -- subscriptions --

    async def add_subscription(self, url: str, name: str = "", fetch_interval: int = 1800) -> int:
        now = time.time()
        row = await self._fetchone(
            """
            INSERT INTO subscriptions (url, name, fetch_interval, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                fetch_interval = excluded.fetch_interval,
                updated_at     = excluded.updated_at
            RETURNING id
            """,
            (url, name, fetch_interval, now, now),
        )
        await self._conn.commit()
        return row["id"]

    async def get_subscription(self, sub_id: int) -> SubscriptionRow | None:
        row = await self._fetchone("SELECT * FROM subscriptions WHERE id = ?", (sub_id,))
        return _row_to_subscription(row) if row else None

    async def list_subscriptions(self) -> list[SubscriptionRow]:
        async with self._conn.execute("SELECT * FROM subscriptions ORDER BY created_at") as cursor:
            return [_row_to_subscription(r) async for r in cursor]

    async def update_subscription_fetch(self, sub_id: int, count: int, *, success: bool) -> None:
        now = time.time()
        if success:
            await self._conn.execute(
                "UPDATE subscriptions SET last_fetch=?, last_fetch_count=?, fail_count=0, updated_at=? WHERE id=?",
                (now, count, now, sub_id),
            )
        else:
            await self._conn.execute(
                "UPDATE subscriptions SET fail_count=fail_count+1, updated_at=? WHERE id=?",
                (now, sub_id),
            )
        await self._conn.commit()

    async def replace_subscription_proxies(self, sub_id: int, configs: list[VlessConfig]) -> list[int]:
        now = time.time()
        new_uris = {c.raw_uri for c in configs}

        async with self._conn.execute(
            "SELECT id, raw_uri FROM proxies WHERE subscription_id = ?", (sub_id,)
        ) as cursor:
            existing = {r["raw_uri"]: r["id"] async for r in cursor}

        try:
            for config in configs:
                await self._conn.execute(
                    """
                    INSERT INTO proxies
                        (raw_uri, uuid, host, port, name, security, type, flow,
                         params_json, status, subscription_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                    ON CONFLICT(raw_uri) DO UPDATE SET
                        uuid            = excluded.uuid,
                        host            = excluded.host,
                        port            = excluded.port,
                        name            = excluded.name,
                        security        = excluded.security,
                        type            = excluded.type,
                        flow            = excluded.flow,
                        params_json     = excluded.params_json,
                        subscription_id = excluded.subscription_id,
                        status          = CASE WHEN proxies.status = 'dead' THEN 'pending' ELSE proxies.status END,
                        updated_at      = excluded.updated_at
                    """,
                    (
                        config.raw_uri, config.uuid, config.host, config.port,
                        config.name, config.security, config.type, config.flow,
                        json.dumps(asdict(config)), sub_id, now, now,
                    ),
                )

            removed_ids = [pid for uri, pid in existing.items() if uri not in new_uris]
            for proxy_id in removed_ids:
                await self._conn.execute("DELETE FROM proxies WHERE id = ?", (proxy_id,))

            await self._conn.commit()
            return removed_ids
        except Exception:
            await self._conn.rollback()
            raise
