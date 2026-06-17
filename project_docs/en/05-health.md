# Health Checker (`core/health.py`)

[Русский](../ru/05-health.md)

## Check flow

Each proxy check runs in two stages:

1. **TCP ping** (`check_proxy_tcp`) — connects to `host:port`. Fast and cheap; fails immediately for unreachable servers.
2. **HTTP check** (`check_proxy`) — only if TCP succeeds. Starts a temporary xray process, sends an HTTP request to `CHECK_URL` through it, expects a response with a status code in `{200, 301, 302, 303, 307, 308, 403, 404, 429, 999}`. Measures latency.

A proxy is marked **active** only if the HTTP check succeeds. TCP failure alone marks it **dead**.

## `HealthChecker`

| Method | Description |
|---|---|
| `check_one(proxy, config, on_status_change?)` | Check a single proxy; update DB; call callback if status changed |
| `check_pending(on_status_change?)` | Check all `pending` proxies concurrently |
| `check_all_active(on_status_change?)` | Check all `active` proxies concurrently |
| `check_dead(on_status_change?)` | Check all `dead` proxies concurrently |

Concurrent checks are batched internally; each proxy is checked independently.

## `HealthResult`

```python
@dataclass
class HealthResult:
    proxy_id: int
    success: bool
    latency_ms: int | None
    status_code: int | None
    error: str
    checked_at: float
    check_url: str
```

## `on_status_change` callback

Called after `check_one` completes if the proxy's status changed. In `ProxyManager`, this callback starts or stops the corresponding xray process and sends a Telegram notification if configured.

The callback fires only on actual status transitions (`active → dead` or `dead/pending → active`). First-time checks (proxy has no previous status) do not trigger notifications.
