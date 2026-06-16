# Health Checker (`core/health.py`)

[Русский](../ru/05-health.md)

## How checks work

Each proxy is verified in two steps:

1. **TCP ping** — `check_proxy_tcp(host, port)` — attempts to open a TCP connection to the server. If TCP fails, the proxy is immediately marked `dead` without launching xray.

2. **HTTP through xray** — `check_proxy(proxy_id, config)` — starts a temporary xray process on port `19900 + (proxy_id % 100)`, makes a GET request to `CHECK_URL` via that SOCKS5 port, and inspects the response status.

After the check the temporary xray process is stopped and its config file is deleted.

## Success status codes

```python
_SUCCESS_STATUSES = {200, 301, 302, 303, 307, 308, 403, 404, 429, 999}
```

Rationale: any of these codes means traffic reached the target — the proxy is alive. 403/404 from LinkedIn means the request went through but was blocked for some reason. A timeout or connection error means dead.

## `HealthResult`

```python
@dataclass
class HealthResult:
    proxy_id: int
    success: bool
    latency_ms: int | None    # set only when success=True
    status_code: int | None
    error: str                 # error description when success=False
    checked_at: float          # unix timestamp
    check_url: str
```

## `HealthChecker`

Main class. Concurrency is capped at 5 simultaneous checks via `asyncio.Semaphore(5)`.

```python
checker = HealthChecker(storage)
```

### Methods

**`check_one(proxy, config, on_status_change=None) → HealthResult`**

Checks a single proxy, updates the DB status, calls `on_status_change(result)` if provided.

**`check_pending(on_status_change=None) → list[HealthResult]`**

Checks all proxies with status `pending`. Called immediately after new links are added.

**`check_all_active(on_status_change=None) → list[HealthResult]`**

Checks all active proxies. Scheduled check — in case some went down.

**`run_forever(on_status_change=None)`**

Infinite loop: check active → check pending → `sleep(CHECK_INTERVAL)`.

## `on_status_change` callback

A synchronous function `(HealthResult) → None`. Called after each check. `HealthChecker` delivers the result here; `ProxyManager` uses it to start/stop xray processes and send Telegram notifications.

The callback is synchronous by design — `HealthChecker` must not depend on manager logic. The manager creates an asyncio task inside the callback.

## Port isolation

Health checks use ports `19900–19999` (formula: `19900 + proxy_id % 100`). These never overlap with the working pool (`10800–10820`), so checks do not interfere with running proxies.
