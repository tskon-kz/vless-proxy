import json
import time
from dataclasses import asdict, dataclass

import aiosqlite

from config import settings
from core.parser import VlessConfig

_CREATE_PROXIES = """
CREATE TABLE IF NOT EXISTS proxies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_uri     TEXT NOT NULL UNIQUE,
    uuid        TEXT NOT NULL,
    host        TEXT NOT NULL,
    port        INTEGER NOT NULL,
    name        TEXT DEFAULT '',
    security    TEXT DEFAULT 'none',
    type        TEXT DEFAULT 'tcp',
    flow        TEXT DEFAULT '',
    params_json TEXT DEFAULT '{}',
    status      TEXT DEFAULT 'pending',
    last_check  REAL,
    latency_ms  INTEGER,
    fail_count  INTEGER DEFAULT 0,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
)
"""

_CREATE_PROCESSES = """
CREATE TABLE IF NOT EXISTS processes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    proxy_id    INTEGER NOT NULL REFERENCES proxies(id) ON DELETE CASCADE,
    local_port  INTEGER NOT NULL UNIQUE,
    pid         INTEGER,
    config_path TEXT NOT NULL,
    started_at  REAL,
    status      TEXT DEFAULT 'stopped'
)
"""

_CREATE_UPDATE_LOG = """
CREATE TABLE IF NOT EXISTS update_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    source     TEXT NOT NULL,
    total      INTEGER,
    valid      INTEGER,
    invalid    INTEGER,
    added      INTEGER,
    removed    INTEGER,
    created_at REAL NOT NULL
)
"""

_CREATE_SUBSCRIPTIONS = """
CREATE TABLE IF NOT EXISTS subscriptions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    url              TEXT NOT NULL UNIQUE,
    name             TEXT DEFAULT '',
    fetch_interval   INTEGER DEFAULT 3600,
    last_fetch       REAL,
    last_fetch_count INTEGER DEFAULT 0,
    fail_count       INTEGER DEFAULT 0,
    created_at       REAL NOT NULL,
    updated_at       REAL NOT NULL
)
"""


@dataclass
class ProxyRow:
    id: int
    raw_uri: str
    host: str
    port: int
    name: str
    security: str
    type: str
    flow: str
    params: dict
    status: str
    last_check: float | None
    latency_ms: int | None
    fail_count: int
    source: str = "manual"
    subscription_id: int | None = None


@dataclass
class ProcessRow:
    id: int
    proxy_id: int
    local_port: int
    pid: int | None
    config_path: str
    status: str


@dataclass
class UpdateStats:
    total: int
    valid: int
    invalid: int
    added: int
    removed: int


@dataclass
class PoolStats:
    active: int
    dead: int
    pending: int
    invalid: int
    running_processes: int


@dataclass
class SubscriptionRow:
    id: int
    url: str
    name: str
    fetch_interval: int
    last_fetch: float | None
    last_fetch_count: int
    fail_count: int
    created_at: float
    updated_at: float


@dataclass
class SubscriptionStats:
    id: int
    name: str
    url: str
    active: int
    pending: int
    dead: int
    total: int
    last_fetch: float | None
    fail_count: int
    fetch_interval: int


def _row_to_proxy(row: aiosqlite.Row) -> ProxyRow:
    try:
        source = row["source"] or "manual"
        subscription_id = row["subscription_id"]
    except (IndexError, KeyError):
        source = "manual"
        subscription_id = None
    return ProxyRow(
        id=row["id"],
        raw_uri=row["raw_uri"],
        host=row["host"],
        port=row["port"],
        name=row["name"] or "",
        security=row["security"] or "none",
        type=row["type"] or "tcp",
        flow=row["flow"] or "",
        params=json.loads(row["params_json"] or "{}"),
        status=row["status"],
        last_check=row["last_check"],
        latency_ms=row["latency_ms"],
        fail_count=row["fail_count"] or 0,
        source=source,
        subscription_id=subscription_id,
    )


def _row_to_subscription(row: aiosqlite.Row) -> SubscriptionRow:
    return SubscriptionRow(
        id=row["id"],
        url=row["url"],
        name=row["name"] or "",
        fetch_interval=row["fetch_interval"] or 3600,
        last_fetch=row["last_fetch"],
        last_fetch_count=row["last_fetch_count"] or 0,
        fail_count=row["fail_count"] or 0,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_process(row: aiosqlite.Row) -> ProcessRow:
    return ProcessRow(
        id=row["id"],
        proxy_id=row["proxy_id"],
        local_port=row["local_port"],
        pid=row["pid"],
        config_path=row["config_path"],
        status=row["status"],
    )


class Storage:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or settings.DB_PATH
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.execute(_CREATE_PROXIES)
        await self._db.execute(_CREATE_PROCESSES)
        await self._db.execute(_CREATE_UPDATE_LOG)
        await self._db.execute(_CREATE_SUBSCRIPTIONS)
        # Reset stale process states from any previous unclean shutdown
        await self._db.execute("UPDATE processes SET status = 'stopped', pid = NULL")
        # Remove duplicate process rows accumulated across restarts (keep latest per proxy)
        await self._db.execute(
            "DELETE FROM processes WHERE rowid NOT IN "
            "(SELECT MAX(rowid) FROM processes GROUP BY proxy_id)"
        )
        # Migrations for existing DBs
        for ddl in (
            "ALTER TABLE proxies ADD COLUMN source TEXT DEFAULT 'manual'",
            "ALTER TABLE proxies ADD COLUMN subscription_id INTEGER",
        ):
            try:
                await self._db.execute(ddl)
            except Exception:
                pass  # column already exists

        # Strip URI fragments from raw_uri (fragments are display names, not part of identity)
        async with self._db.execute(
            "SELECT id, raw_uri FROM proxies WHERE raw_uri LIKE '%#%'"
        ) as cursor:
            rows = await cursor.fetchall()
        for row in rows:
            canonical = row["raw_uri"].split("#")[0]
            async with self._db.execute(
                "SELECT id FROM proxies WHERE raw_uri = ? AND id != ?",
                (canonical, row["id"]),
            ) as dup_cursor:
                dup = await dup_cursor.fetchone()
            if dup:
                await self._db.execute("DELETE FROM proxies WHERE id = ?", (row["id"],))
            else:
                await self._db.execute(
                    "UPDATE proxies SET raw_uri = ? WHERE id = ?",
                    (canonical, row["id"]),
                )

        # Deduplicate proxies by (host, port) per subscription.
        # For each group keep the row with best status (active > pending > dead)
        # and lowest id as tiebreaker; delete the rest.
        await self._db.execute(
            """
            DELETE FROM proxies
            WHERE subscription_id IS NOT NULL
              AND id NOT IN (
                SELECT id FROM proxies p
                WHERE subscription_id IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM proxies p2
                    WHERE p2.subscription_id = p.subscription_id
                      AND p2.host = p.host
                      AND p2.port = p.port
                      AND p2.id != p.id
                      AND (
                        CASE p2.status WHEN 'active' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END
                        < CASE p.status WHEN 'active' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END
                        OR (
                          CASE p2.status WHEN 'active' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END
                          = CASE p.status WHEN 'active' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END
                          AND p2.id < p.id
                        )
                      )
                  )
              )
            """
        )
        await self._db.commit()

    @property
    def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Storage.init() has not been called")
        return self._db

    async def upsert_proxy(self, config: VlessConfig) -> int:
        now = time.time()
        params_json = json.dumps(asdict(config))
        async with self._conn.execute(
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
                params_json, now, now,
            ),
        ) as cursor:
            row = await cursor.fetchone()
        await self._conn.commit()
        return row["id"]

    async def set_proxy_status(
        self,
        proxy_id: int,
        status: str,
        latency_ms: int | None = None,
    ) -> None:
        now = time.time()
        if status == "active":
            await self._conn.execute(
                """
                UPDATE proxies
                SET status = ?, last_check = ?, latency_ms = ?,
                    fail_count = 0, updated_at = ?
                WHERE id = ?
                """,
                (status, now, latency_ms, now, proxy_id),
            )
        elif status == "dead":
            await self._conn.execute(
                """
                UPDATE proxies
                SET status = ?, last_check = ?, latency_ms = NULL,
                    fail_count = fail_count + 1, updated_at = ?
                WHERE id = ?
                """,
                (status, now, now, proxy_id),
            )
        else:
            await self._conn.execute(
                """
                UPDATE proxies
                SET status = ?, last_check = ?, latency_ms = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, now, latency_ms, now, proxy_id),
            )
        await self._conn.commit()

    async def get_active_proxies(self) -> list[ProxyRow]:
        async with self._conn.execute(
            "SELECT * FROM proxies WHERE status = 'active'"
        ) as cursor:
            return [_row_to_proxy(r) async for r in cursor]

    async def get_pending_proxies(self) -> list[ProxyRow]:
        async with self._conn.execute(
            "SELECT * FROM proxies WHERE status = 'pending'"
        ) as cursor:
            return [_row_to_proxy(r) async for r in cursor]

    async def get_dead_proxies(self) -> list[ProxyRow]:
        async with self._conn.execute(
            "SELECT * FROM proxies WHERE status = 'dead'"
        ) as cursor:
            return [_row_to_proxy(r) async for r in cursor]

    async def get_all_proxies(self) -> list[ProxyRow]:
        async with self._conn.execute("SELECT * FROM proxies") as cursor:
            return [_row_to_proxy(r) async for r in cursor]

    async def get_proxy_by_id(self, proxy_id: int) -> ProxyRow | None:
        async with self._conn.execute(
            "SELECT * FROM proxies WHERE id = ?", (proxy_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return _row_to_proxy(row) if row else None

    async def replace_all(
        self, configs: list[VlessConfig], source: str
    ) -> UpdateStats:
        now = time.time()
        new_uris = {c.raw_uri for c in configs}

        # Only manage manually-added proxies; leave subscription proxies untouched
        async with self._conn.execute(
            "SELECT id, raw_uri FROM proxies WHERE subscription_id IS NULL AND status != 'dead'"
        ) as cursor:
            existing = {r["raw_uri"]: r["id"] async for r in cursor}

        added = 0
        removed = 0

        try:
            for config in configs:
                if config.raw_uri not in existing:
                    added += 1
                params_json = json.dumps(asdict(config))
                await self._conn.execute(
                    """
                    INSERT INTO proxies
                        (raw_uri, uuid, host, port, name, security, type, flow,
                         params_json, status, source, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                    ON CONFLICT(raw_uri) DO UPDATE SET
                        uuid        = excluded.uuid,
                        host        = excluded.host,
                        port        = excluded.port,
                        name        = excluded.name,
                        security    = excluded.security,
                        type        = excluded.type,
                        flow        = excluded.flow,
                        params_json = excluded.params_json,
                        source      = excluded.source,
                        status      = CASE WHEN proxies.status = 'dead' THEN 'pending' ELSE proxies.status END,
                        updated_at  = excluded.updated_at
                    WHERE proxies.subscription_id IS NULL
                    """,
                    (
                        config.raw_uri, config.uuid, config.host, config.port,
                        config.name, config.security, config.type, config.flow,
                        params_json, source, now, now,
                    ),
                )

            for uri, proxy_id in existing.items():
                if uri not in new_uris:
                    removed += 1
                    await self._conn.execute(
                        "UPDATE proxies SET status = 'dead', updated_at = ? WHERE id = ?",
                        (now, proxy_id),
                    )

            stats = UpdateStats(
                total=len(configs),
                valid=len(configs),
                invalid=0,
                added=added,
                removed=removed,
            )
            await self._conn.execute(
                """
                INSERT INTO update_log
                    (source, total, valid, invalid, added, removed, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (source, stats.total, stats.valid, stats.invalid,
                 stats.added, stats.removed, now),
            )
            await self._conn.commit()
        except Exception:
            await self._conn.rollback()
            raise

        return stats

    async def get_process(self, proxy_id: int) -> ProcessRow | None:
        async with self._conn.execute(
            "SELECT * FROM processes WHERE proxy_id = ?", (proxy_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return _row_to_process(row) if row else None

    async def upsert_process(
        self, proxy_id: int, local_port: int, config_path: str
    ) -> None:
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

    async def set_process_pid(
        self, proxy_id: int, local_port: int, pid: int | None, status: str
    ) -> None:
        now = time.time()
        await self._conn.execute(
            """
            UPDATE processes
            SET pid = ?, status = ?, started_at = ?
            WHERE proxy_id = ? AND local_port = ?
            """,
            (pid, status, now if pid is not None else None, proxy_id, local_port),
        )
        await self._conn.commit()

    async def get_available_port(self) -> int | None:
        async with self._conn.execute(
            "SELECT local_port FROM processes WHERE status = 'running'"
        ) as cursor:
            used = {r["local_port"] async for r in cursor}

        for port in range(settings.PROXY_PORT_START, settings.PROXY_PORT_END + 1):
            if port not in used:
                return port
        return None

    async def log_update(self, source: str, stats: UpdateStats) -> None:
        now = time.time()
        await self._conn.execute(
            """
            INSERT INTO update_log
                (source, total, valid, invalid, added, removed, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (source, stats.total, stats.valid, stats.invalid,
             stats.added, stats.removed, now),
        )
        await self._conn.commit()

    async def get_stats(self) -> PoolStats:
        async with self._conn.execute(
            """
            SELECT
                SUM(status = 'active')  AS active,
                SUM(status = 'dead')    AS dead,
                SUM(status = 'pending') AS pending,
                SUM(status = 'invalid') AS invalid
            FROM proxies
            """
        ) as cursor:
            row = await cursor.fetchone()

        async with self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM processes WHERE status = 'running'"
        ) as cursor:
            proc_row = await cursor.fetchone()

        return PoolStats(
            active=row["active"] or 0,
            dead=row["dead"] or 0,
            pending=row["pending"] or 0,
            invalid=row["invalid"] or 0,
            running_processes=proc_row["cnt"] or 0,
        )

    async def get_pending_by_subscription(self, sub_id: int) -> ProxyRow | None:
        async with self._conn.execute(
            "SELECT * FROM proxies WHERE subscription_id = ? AND status = 'pending' LIMIT 1",
            (sub_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return _row_to_proxy(row) if row else None

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    async def add_subscription(
        self, url: str, name: str = "", fetch_interval: int = 3600
    ) -> int:
        now = time.time()
        async with self._conn.execute(
            """
            INSERT INTO subscriptions (url, name, fetch_interval, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                name           = excluded.name,
                fetch_interval = excluded.fetch_interval,
                updated_at     = excluded.updated_at
            RETURNING id
            """,
            (url, name, fetch_interval, now, now),
        ) as cursor:
            row = await cursor.fetchone()
        await self._conn.commit()
        return row["id"]

    async def get_subscription(self, sub_id: int) -> SubscriptionRow | None:
        async with self._conn.execute(
            "SELECT * FROM subscriptions WHERE id = ?", (sub_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return _row_to_subscription(row) if row else None

    async def get_subscription_by_url(self, url: str) -> SubscriptionRow | None:
        async with self._conn.execute(
            "SELECT * FROM subscriptions WHERE url = ?", (url,)
        ) as cursor:
            row = await cursor.fetchone()
        return _row_to_subscription(row) if row else None

    async def list_subscriptions(self) -> list[SubscriptionRow]:
        async with self._conn.execute(
            "SELECT * FROM subscriptions ORDER BY created_at"
        ) as cursor:
            return [_row_to_subscription(r) async for r in cursor]

    async def delete_subscription(self, sub_id: int) -> None:
        await self._conn.execute(
            "DELETE FROM subscriptions WHERE id = ?", (sub_id,)
        )
        await self._conn.commit()

    async def delete_subscription_proxies(self, sub_id: int) -> None:
        now = time.time()
        await self._conn.execute(
            "UPDATE proxies SET status = 'dead', updated_at = ? WHERE subscription_id = ?",
            (now, sub_id),
        )
        await self._conn.commit()

    async def update_subscription_fetch(
        self, sub_id: int, count: int, *, success: bool
    ) -> None:
        now = time.time()
        if success:
            await self._conn.execute(
                """
                UPDATE subscriptions
                SET last_fetch = ?, last_fetch_count = ?, fail_count = 0, updated_at = ?
                WHERE id = ?
                """,
                (now, count, now, sub_id),
            )
        else:
            await self._conn.execute(
                """
                UPDATE subscriptions
                SET fail_count = fail_count + 1, updated_at = ?
                WHERE id = ?
                """,
                (now, sub_id),
            )
        await self._conn.commit()

    async def replace_subscription_proxies(
        self, sub_id: int, configs: list[VlessConfig]
    ) -> UpdateStats:
        now = time.time()
        new_uris = {c.raw_uri for c in configs}
        source = f"subscription:{sub_id}"

        async with self._conn.execute(
            "SELECT id, raw_uri FROM proxies WHERE subscription_id = ? AND status != 'dead'",
            (sub_id,),
        ) as cursor:
            existing = {r["raw_uri"]: r["id"] async for r in cursor}

        added = 0
        removed = 0

        try:
            for config in configs:
                if config.raw_uri not in existing:
                    added += 1
                params_json = json.dumps(asdict(config))
                await self._conn.execute(
                    """
                    INSERT INTO proxies
                        (raw_uri, uuid, host, port, name, security, type, flow,
                         params_json, status, source, subscription_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
                    ON CONFLICT(raw_uri) DO UPDATE SET
                        uuid            = excluded.uuid,
                        host            = excluded.host,
                        port            = excluded.port,
                        name            = excluded.name,
                        security        = excluded.security,
                        type            = excluded.type,
                        flow            = excluded.flow,
                        params_json     = excluded.params_json,
                        source          = excluded.source,
                        subscription_id = excluded.subscription_id,
                        status          = CASE WHEN proxies.status = 'dead' THEN 'pending' ELSE proxies.status END,
                        updated_at      = excluded.updated_at
                    """,
                    (
                        config.raw_uri, config.uuid, config.host, config.port,
                        config.name, config.security, config.type, config.flow,
                        params_json, source, sub_id, now, now,
                    ),
                )

            for uri, proxy_id in existing.items():
                if uri not in new_uris:
                    removed += 1
                    await self._conn.execute(
                        "UPDATE proxies SET status = 'dead', updated_at = ? WHERE id = ?",
                        (now, proxy_id),
                    )

            stats = UpdateStats(
                total=len(configs),
                valid=len(configs),
                invalid=0,
                added=added,
                removed=removed,
            )
            await self._conn.execute(
                """
                INSERT INTO update_log (source, total, valid, invalid, added, removed, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (source, stats.total, stats.valid, stats.invalid,
                 stats.added, stats.removed, now),
            )
            await self._conn.commit()
        except Exception:
            await self._conn.rollback()
            raise

        return stats

    async def list_subscription_stats(self) -> list[SubscriptionStats]:
        subs = await self.list_subscriptions()
        result = []
        for sub in subs:
            async with self._conn.execute(
                """
                SELECT
                    SUM(status = 'active')  AS active,
                    SUM(status = 'dead')    AS dead,
                    SUM(status = 'pending') AS pending,
                    COUNT(*)                AS total
                FROM proxies WHERE subscription_id = ?
                """,
                (sub.id,),
            ) as cursor:
                row = await cursor.fetchone()
            result.append(
                SubscriptionStats(
                    id=sub.id,
                    name=sub.name,
                    url=sub.url,
                    active=row["active"] or 0,
                    pending=row["pending"] or 0,
                    dead=row["dead"] or 0,
                    total=row["total"] or 0,
                    last_fetch=sub.last_fetch,
                    fail_count=sub.fail_count,
                    fetch_interval=sub.fetch_interval,
                )
            )
        return result

    async def get_subscription_stats(self, sub_id: int) -> SubscriptionStats | None:
        sub = await self.get_subscription(sub_id)
        if sub is None:
            return None
        async with self._conn.execute(
            """
            SELECT
                SUM(status = 'active')  AS active,
                SUM(status = 'dead')    AS dead,
                SUM(status = 'pending') AS pending,
                COUNT(*)                AS total
            FROM proxies WHERE subscription_id = ?
            """,
            (sub_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return SubscriptionStats(
            id=sub.id,
            name=sub.name,
            url=sub.url,
            active=row["active"] or 0,
            pending=row["pending"] or 0,
            dead=row["dead"] or 0,
            total=row["total"] or 0,
            last_fetch=sub.last_fetch,
            fail_count=sub.fail_count,
            fetch_interval=sub.fetch_interval,
        )

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None
