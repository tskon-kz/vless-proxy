# Orchestrator (`core/manager.py`)

[Русский](../ru/06-manager.md)

## Role

`ProxyManager` is the central component connecting Storage, XrayProcessPool, and HealthChecker. All input channels (bot, file, API) go through it exclusively.

## Initialisation

```python
storage = Storage(settings.DB_PATH)
manager = ProxyManager(storage)
await manager.startup()
```

`startup()`:
1. Initialises the DB
2. Restores xray processes for all `active` proxies from the DB
3. Kicks off health checks for `pending` proxies in the background
4. Starts the infinite health-check loop (`run_forever`)

## Adding proxies

```python
report = await manager.update_proxies(raw_links, source="telegram")
```

`update_proxies()` runs under `asyncio.Lock`:
1. Parses links via `parse_vless_list`
2. Calls `storage.replace_all` — saves to DB, marks missing as `dead`
3. Stops xray processes for removed proxies
4. Starts health checks for new `pending` proxies in the background

Returns `UpdateReport`:

```python
@dataclass
class UpdateReport:
    total_received: int   # len(raw_links) — all incoming strings
    valid: int            # successfully parsed
    invalid: int          # total_received - valid
    parse_errors: list[str]
    newly_added: int      # new (not in DB before)
    already_known: int    # updated (already existed)
    removed: int          # marked dead
    source: str           # "telegram" / "file" / "api"
```

## Reacting to status changes

When a health check completes it calls the synchronous `_status_change_callback`, which creates an `_on_health_change` task:

```
proxy alive  → process_pool.start_proxy()   (if not already running)
proxy dead   → process_pool.stop_proxy()    (if was running)
             → notify_callback(proxy, result)  (if configured)
```

## Telegram notifications

```python
manager.notify_callback: Callable[[ProxyRow, HealthResult], Awaitable[None]] | None
```

Set by `bot.py` when `TG_NOTIFY_CHAT_ID` is configured. Receives raw data — text formatting stays in `bot/strings.py`; the manager knows nothing about Telegram.

## Getting a proxy for a client

```python
info = await manager.get_proxy_for_client()   # random active proxy
status = await manager.get_status()            # full pool status
```

`get_proxy_for_client()` shuffles the active list and returns the first one with a running process.

## Background tasks

To prevent background tasks from being garbage-collected (asyncio does not hold strong references), the manager keeps them in `_background_tasks: set[asyncio.Task]` and removes them on completion via `done_callback`.

On `shutdown()` all background tasks are cancelled, xray processes are stopped, and the DB connection is closed.
