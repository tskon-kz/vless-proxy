# Architecture Overview

[Русский](../ru/00-overview.md)

## What the service does

Fetches VLESS server lists from subscriptions, validates and health-checks each server via xray-core, and maintains a pool of working SOCKS5 proxies on local ports. The fastest server is always available at `PROXY_PORT_START`.

## Components

```
main.py
├── ProxyManager              — central orchestrator
│   ├── Storage               — SQLite database
│   ├── XrayProcessPool       — pool of persistent xray processes
│   ├── HealthChecker         — proxy liveness checks
│   └── SubscriptionManager   — subscription fetch/refresh tasks
├── FastAPI (uvicorn)         — REST API
└── Bot + Dispatcher          — Telegram bot (aiogram 3)
```

## Proxy lifecycle

```
SUBSCRIPTION_URLS (from .env)
          │
          ▼
  SubscriptionFetcher         fetch + base64-decode
          │
          ▼
    parse_vless_list()        parse and validate URIs
          │
          ▼
  replace_subscription_proxies()
    new URIs  → status: pending
    removed   → status: dead
          │
          ▼
    HealthChecker             TCP ping → HTTP through a temp xray
          │
     ┌────┴────┐
   alive      dead
     │
     ▼
XrayProcessPool               start persistent xray process
     │
     ▼
socks5://PROXY_BIND_HOST:<port>   available via API
```

## Proxy statuses

| Status | Meaning |
|---|---|
| `pending` | Just added or returned from subscription refresh; not yet checked |
| `active` | Alive; a persistent xray process is running on a SOCKS5 port |
| `dead` | Failed health check; rechecked every 3rd health cycle |

## Port assignment

Active proxies are sorted by latency after each health cycle. The fastest gets `PROXY_PORT_START`, the next `PROXY_PORT_START + 1`, and so on. `/proxy/best` always returns `PROXY_PORT_START`.

## Startup behaviour

On every startup the proxy table is wiped and `last_fetch` is reset to `NULL`, so subscriptions are fetched immediately. This prevents stale data from accumulating across restarts.
