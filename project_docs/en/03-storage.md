# Storage (`core/storage.py`)

[Русский](../ru/03-storage.md)

SQLite database via `aiosqlite`. WAL mode is enabled. Foreign keys are enforced.

## Tables

### `proxies`

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | |
| `raw_uri` | TEXT UNIQUE | Canonical URI without fragment (identity key) |
| `uuid`, `host`, `port`, `name` | TEXT/INTEGER | Parsed fields |
| `security`, `type`, `flow` | TEXT | Transport parameters |
| `params_json` | TEXT | Full `VlessConfig` serialized as JSON |
| `status` | TEXT | `pending` / `active` / `dead` |
| `last_check` | REAL | Unix timestamp of last health check |
| `latency_ms` | INTEGER | Last successful check latency |
| `fail_count` | INTEGER | Consecutive failure count |
| `subscription_id` | INTEGER | FK to `subscriptions` |

### `processes`

Tracks running xray processes. One row per proxy, keyed by `local_port` (UNIQUE).

### `subscriptions`

| Column | Description |
|---|---|
| `url` | Subscription URL (UNIQUE) |
| `fetch_interval` | Refresh interval in seconds |
| `last_fetch` | Timestamp of last successful fetch (NULL after restart) |
| `last_fetch_count` | Number of proxies returned by last fetch |
| `fail_count` | Consecutive fetch failure count |

## Key methods

| Method | Description |
|---|---|
| `init()` | Create tables, run schema migrations, **wipe proxies**, reset `last_fetch` |
| `upsert_proxy(config)` | Insert or update proxy; returns `id`; does not change status on conflict |
| `replace_subscription_proxies(sub_id, configs)` | Atomic: insert/reset new URIs as pending; mark removed URIs as dead |
| `set_proxy_status(id, status, latency_ms?)` | Update status; active resets `fail_count`; dead increments it |
| `get_active_proxies()` | All proxies with `status = 'active'` |
| `get_pending_proxies()` | All proxies with `status = 'pending'` |
| `get_dead_proxies()` | All proxies with `status = 'dead'` |
| `get_available_port()` | Lowest unused port in `PROXY_PORT_START..PROXY_PORT_END` range |
| `get_stats()` | Returns `PoolStats(active, dead, pending, running_processes)` |

## Startup wipe

`init()` runs `DELETE FROM proxies` and `UPDATE subscriptions SET last_fetch = NULL` on every startup. This ensures the DB never accumulates stale proxy records across restarts, and causes subscription pollers to fetch immediately.
