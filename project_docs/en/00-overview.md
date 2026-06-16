# Architecture Overview

[Русский](../ru/00-overview.md)

## What the service does

Accepts VLESS links from three sources (Telegram bot, `vless.txt` file, REST API), validates them, checks liveness via xray-core, and maintains a pool of working SOCKS5 proxies on local ports.

## Components

```
main.py
├── ProxyManager              — central orchestrator
│   ├── Storage               — SQLite database
│   ├── XrayProcessPool       — pool of xray processes
│   ├── HealthChecker         — proxy liveness checks
│   └── SubscriptionManager   — subscription polling tasks
├── FileWatcher               — watches vless.txt for changes
├── FastAPI (uvicorn)         — REST API
└── Bot + Dispatcher          — Telegram bot (aiogram 3)
```

## Proxy lifecycle

```
Incoming links (bot / file / API / subscription)
          │
          ▼
    parse_vless()              parse and validate URI
          │
          ▼
  storage.replace_all()        save to DB, status → pending
  (or replace_subscription_proxies for subscriptions)
          │
          ▼
    HealthChecker              TCP ping + HTTP through a temporary xray
          │
     ┌────┴────┐
   alive      dead
     │          └──► if subscription proxy: promote next pending
     ▼               from the same subscription
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
| aiohttp | HTTP client in health checker and subscription fetcher |
| FastAPI + uvicorn | REST API |
| aiogram 3 | Telegram bot |
| xray-core | External Go binary; tunnels traffic |

## Module index

| File | Module doc |
|---|---|
| `config.py` | [Configuration](01-config.md) |
| `core/parser.py` | [VLESS link parser](02-parser.md) |
| `core/storage.py` | [Storage (SQLite)](03-storage.md) |
| `core/xray.py` | [xray-core management](04-xray.md) |
| `core/health.py` | [Health checker](05-health.md) |
| `core/manager.py` | [Orchestrator](06-manager.md) |
| `api/server.py` | [REST API](07-api.md) |
| `bot/bot.py` | [Telegram bot](08-bot.md) |
| `core/watcher.py` | [File watcher](09-watcher.md) |
| systemd | [Deployment](10-systemd.md) |
| `core/subscription.py` | [Subscriptions](11-subscription.md) |
