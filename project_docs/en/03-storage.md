# Storage (`core/storage.py`)

[Русский](../ru/03-storage.md)

## Overview

A thin async wrapper around SQLite via aiosqlite. All methods are async. The DB is initialised with `await storage.init()`.

```python
storage = Storage("./state.db")
await storage.init()
```

## Schema

### `proxies`

Main table. One row = one VLESS server.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `raw_uri` | TEXT UNIQUE | Original link string — unique key |
| `uuid`, `host`, `port` | TEXT/INT | Fast-query fields |
| `name`, `security`, `type`, `flow` | TEXT | Connection parameters |
| `params_json` | TEXT | Full `VlessConfig` serialised as JSON |
| `status` | TEXT | `pending` / `active` / `dead` |
| `last_check` | REAL | Unix timestamp of last check |
| `latency_ms` | INTEGER | Latency of last successful check |
| `fail_count` | INTEGER | Consecutive failure counter |

### `processes`

Running xray processes. One row = one active proxy.

| Column | Description |
|--------|-------------|
| `proxy_id` | FK → proxies.id |
| `local_port` | UNIQUE — occupied local port |
| `pid` | xray process PID (NULL if not running) |
| `config_path` | Path to the xray JSON config |
| `status` | `stopped` / `running` / `crashed` |

### `update_log`

Log of pool updates. Written on every `replace_all` call.

## Key methods

### `upsert_proxy(config) → int`

Inserts a new proxy or updates the metadata of an existing one (matched by `raw_uri`). **Status is not changed on conflict** — an `active` proxy stays `active`.

Returns the row `id`.

### `replace_all(configs, source) → UpdateStats`

Atomic pool update:

1. All links in `configs` — upsert (status unchanged on conflict)
2. Everything in the DB with status ≠ `dead` that is not in `configs` — marked `dead`
3. A record is written to `update_log` with the source and statistics

Runs in a transaction — rolls back on error.

### `set_proxy_status(proxy_id, status, latency_ms)`

Updates proxy status:
- `active` → resets `fail_count = 0`, writes `latency_ms`
- `dead` → increments `fail_count + 1`, clears `latency_ms`

### `get_available_port() → int | None`

Returns the first free port in the `PROXY_PORT_START..PROXY_PORT_END` range. A port is considered occupied if there is a `processes` row with status `running`.

### `get_stats() → PoolStats`

Returns aggregate counters: active, dead, pending, invalid, running_processes.

## Dataclasses

```python
@dataclass
class ProxyRow:
    id: int; raw_uri: str; host: str; port: int; name: str
    security: str; type: str; flow: str; params: dict
    status: str; last_check: float | None
    latency_ms: int | None; fail_count: int

@dataclass
class ProcessRow:
    id: int; proxy_id: int; local_port: int
    pid: int | None; config_path: str; status: str

@dataclass
class PoolStats:
    active: int; dead: int; pending: int; invalid: int
    running_processes: int
```

## DB settings

On initialisation:
- `PRAGMA journal_mode=WAL` — Write-Ahead Logging for concurrent reads
- `PRAGMA foreign_keys=ON` — cascades process deletion when a proxy is deleted
