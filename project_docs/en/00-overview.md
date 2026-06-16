# Architecture Overview

[Русский](../ru/00-overview.md)

## What the service does

Accepts VLESS links from three sources (Telegram bot, `vless.txt` file, REST API), validates them, checks liveness via xray-core, and maintains a pool of working SOCKS5 proxies on local ports.

## Components

```
main.py
├── ProxyManager          — central orchestrator
│   ├── Storage           — SQLite database
│   ├── XrayProcessPool   — pool of xray processes
│   └── HealthChecker     — proxy liveness checks
├── FileWatcher           — watches vless.txt for changes
├── FastAPI (uvicorn)     — REST API
└── Bot + Dispatcher      — Telegram bot (aiogram 3)
```

## Proxy lifecycle

```
Incoming links (bot / file / API)
          │
          ▼
    parse_vless()              parse and validate URI
          │
          ▼
  storage.replace_all()        save to DB, status → pending
          │
          ▼
    HealthChecker              TCP ping + HTTP through a temporary xray
          │
     ┌────┴────┐
   alive      dead
     │
     ▼
XrayProcessPool                start a persistent xray process
     │
     ▼
socks5://127.0.0.1:<port>      available to clients via API
```

## Proxy statuses

| Status    | When                                              |
|-----------|---------------------------------------------------|
| `pending` | Just added, not yet checked                       |
| `active`  | Alive, xray process is running                    |
| `dead`    | Failed health check; `fail_count` increments      |

## Ports

- **10800–10820** — SOCKS5 pool ports (`PROXY_PORT_START` / `PROXY_PORT_END`)
- **19900–19999** — temporary health-check ports; never overlap with the pool

## State persistence

The single source of truth is SQLite (`state.db`). `vless.txt` is a temporary input channel: deleted after loading. On restart, active proxies are restored from the DB and their xray processes are relaunched.

## Stack

| Library | Role |
|---|---|
| pydantic-settings | Configuration via env / `.env` |
| aiosqlite | Async SQLite |
| aiohttp | HTTP client in health checker |
| FastAPI + uvicorn | REST API |
| aiogram 3 | Telegram bot |
| xray-core | External Go binary; tunnels traffic |
