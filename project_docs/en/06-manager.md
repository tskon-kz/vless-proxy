# Manager / Orchestrator (`core/manager.py`)

[Русский](../ru/06-manager.md)

`ProxyManager` is the central component that ties storage, xray processes, health checks, and subscriptions together.

## Startup

```python
await manager.startup()
```

1. Calls `storage.init()` — wipes proxy DB, resets subscription `last_fetch`.
2. Starts `SubscriptionManager` — launches a poller task per subscription; each fetches immediately (since `last_fetch = NULL`).
3. Starts the health check loop.

## Health loop

Runs every `CHECK_INTERVAL` seconds (default 5 min):

```
sleep CHECK_INTERVAL
→ check_all_active
→ check_pending
→ check_dead  (every 3rd cycle only)
→ reorder by latency
```

## Status change handling (`_on_health_change`)

Called after every health check that changes a proxy's status:

- **Went active** → start xray process if not already running.
- **Went dead** → stop xray process if running.
- **Notification** → send Telegram message if `TG_NOTIFY_CHAT_ID` is set and the proxy has a previously known status (no notifications on first appearance).

## Port reordering (`_reorder_by_latency`)

After each check cycle, active proxies are sorted by `latency_ms`. The fastest is moved to `PROXY_PORT_START`, the second fastest to `PROXY_PORT_START + 1`, etc. Proxies that are already on the correct port are not restarted.

## `ProxyManager.get_status() → ManagerStatus`

Returns:
- `pool_stats: PoolStats` — counts of active/dead/pending proxies and running processes
- `active_proxies: list[ProxyInfo]` — name, host, local port, latency for each running proxy
- `uptime_seconds: float`

## `ProxyManager.force_recheck()`

Runs a full active + pending check cycle immediately (used by `/check` bot command).
