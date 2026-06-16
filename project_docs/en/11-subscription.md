# Subscriptions (`core/subscription.py`)

[Русский](../ru/11-subscription.md)

## Purpose

Subscriptions allow importing VLESS proxy lists from external URLs automatically, without manually passing links every time. A subscription is a URL that returns a text file with `vless://` links (plain or base64-encoded). The service fetches it on startup and then periodically, and replaces the subscription's proxy set with the fresh list.

## Key concepts

- Each subscription has its own set of proxies in the DB (`subscription_id` column).
- Subscription proxies and manually-added proxies are **isolated**: a `/update` API call or Telegram message never deletes subscription proxies, and a subscription refresh never deletes manually-added proxies.
- When a subscription proxy dies, the manager automatically promotes a pending proxy **from the same subscription** to check next — no manual intervention needed.
- Each subscription runs its own background polling task.

## Response format

The fetcher accepts two formats:

**Plain text** — one `vless://` link per line:
```
vless://uuid1@host1:443?security=tls&...#Name1
vless://uuid2@host2:443?security=tls&...#Name2
```

**Base64** — the same content, base64-encoded (common for clash/v2ray subscription servers). The fetcher detects base64 automatically: decodes, checks for `vless://` inside; if not found — treats as plain text.

Request uses `User-Agent: clash/1.18.0` for compatibility with most subscription servers.

## Components

### `SubscriptionFetcher`

Makes the HTTP GET request and decodes the body.

| Method | Description |
|---|---|
| `fetch(url) → FetchResult` | GET request, decode, extract `vless://` links |
| `_decode_body(body) → str` | Try base64 decode; fallback to plain text |

### `SubscriptionManager`

Orchestrates all subscriptions. Created by `ProxyManager` on startup.

| Method | Description |
|---|---|
| `startup()` | Load all subscriptions from DB, start polling tasks |
| `shutdown()` | Cancel all polling tasks |
| `add_subscription(url, name, fetch_interval) → (id, FetchResult)` | Add new subscription, fetch immediately, start poller |
| `add_or_refresh(url) → FetchResult` | Add if new, refresh if already known |
| `refresh_subscription(sub_id) → FetchResult` | Fetch and replace proxies for one subscription |
| `refresh_all() → list[FetchResult]` | Refresh all subscriptions |
| `remove_subscription(sub_id)` | Cancel poller, mark proxies dead, delete from DB |
| `get_subscription(sub_id)` | Get subscription row |
| `list_subscriptions()` | List all subscriptions with proxy stats |

### `FetchResult`

```python
@dataclass
class FetchResult:
    url: str
    success: bool
    links: list[str]   # raw vless:// lines extracted
    count: int         # number of valid links (after parse)
    error: str         # non-empty on failure
```

## DB schema

### `subscriptions` table

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `url` | TEXT UNIQUE | Subscription URL |
| `name` | TEXT | Human-readable label |
| `fetch_interval` | INTEGER | Polling interval, seconds (default 3600) |
| `last_fetch` | REAL | Unix timestamp of last successful fetch |
| `last_fetch_count` | INTEGER | Number of proxies in last successful fetch |
| `fail_count` | INTEGER | Consecutive failures |

### `proxies` table additions

Two columns were added to the existing `proxies` table:

| Column | Description |
|---|---|
| `source` | Origin: `'manual'`, `'file'`, `'telegram'`, `'api'`, or `'subscription:<id>'` |
| `subscription_id` | FK to `subscriptions.id`; `NULL` for manual proxies |

Migration runs automatically on startup via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.

## Polling lifecycle

```
startup()
  └── for each sub in DB:
        _start_poller(sub)  →  asyncio.Task in self._tasks[sub_id]

poller task:
  loop:
    sleep(remaining time until next fetch)
    refresh_subscription(sub_id)
    update sub.fetch_interval, sub.last_fetch from DB
```

The initial sleep is calculated as `fetch_interval - elapsed_since_last_fetch`. If the subscription has never been fetched (`last_fetch = None`), sleeps the full `fetch_interval`. If the interval has already passed, sleeps 0 (fires immediately).

## Dead proxy replacement

When a proxy from a subscription is declared dead by the health checker, `ProxyManager._on_health_change` calls `_replace_dead_from_subscription`:

1. Check `proxy.subscription_id`
2. Query `proxies WHERE subscription_id = sub_id AND status = 'pending' LIMIT 1`
3. If found: trigger `health_checker.check_one_by_id(candidate.id)` in background
4. If none: log and do nothing (wait for next subscription refresh)

This keeps the active proxy count stable without waiting for the next scheduled refresh.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `SUBSCRIPTION_FETCH_INTERVAL` | `3600` | Default polling interval, seconds |
| `SUBSCRIPTION_TIMEOUT` | `30` | HTTP request timeout, seconds |
| `SUBSCRIPTION_MAX_RETRIES` | `3` | (reserved for future retry logic) |

## Adding via `vless.txt`

HTTP/HTTPS lines in `vless.txt` are treated as subscription URLs:

```
# vless:// lines → manual proxies
vless://uuid@host:443?...#Name

# http/https lines → subscription URLs
https://sub.example.com/token123
```

On load: `add_or_refresh(url)` is called for each URL — adds if new, refreshes if already known.

## Telegram bot commands

| Command | Description |
|---|---|
| `/sub_add <url> [name]` | Add subscription and do initial fetch |
| `/sub_list` | Show all subscriptions with proxy counts |
| `/sub_refresh [id]` | Refresh one subscription (or all if no ID) |
| `/sub_remove <id>` | Show confirmation prompt |
| `/sub_remove <id> confirm` | Delete subscription and all its proxies |

## REST API endpoints

All endpoints require `Authorization: Bearer <API_SECRET_KEY>`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/subscriptions` | List all subscriptions with stats |
| `POST` | `/subscriptions` | Add new subscription |
| `DELETE` | `/subscriptions/{id}` | Remove subscription and its proxies |
| `POST` | `/subscriptions/{id}/refresh` | Trigger immediate refresh |

### POST /subscriptions

```json
{
  "url": "https://sub.example.com/token",
  "name": "My Provider",
  "fetch_interval": 3600
}
```

Returns `SubscriptionAddResponse`:
```json
{"id": 1, "url": "...", "name": "My Provider", "fetched": 42}
```

### GET /subscriptions

Returns a list of `SubscriptionResponse` objects, each including:
- `id`, `url`, `name`, `fetch_interval`, `last_fetch`, `fail_count`
- `active`, `pending`, `dead`, `total` — proxy counts for this subscription
