# Subscriptions (`core/subscription.py`)

[Русский](../ru/11-subscription.md)

Subscriptions are the only source of proxy servers. Each subscription is a URL that returns a list of `vless://` links, either as plain text or base64-encoded.

## Configuration

```env
SUBSCRIPTION_URLS=["https://sub.example.com/token"]
SUBSCRIPTION_FETCH_INTERVAL=1800   # seconds, default 30 min
SUBSCRIPTION_TIMEOUT=30            # fetch timeout, seconds
```

Multiple subscriptions:
```env
SUBSCRIPTION_URLS=["https://sub1.example.com/token","https://sub2.example.com/token"]
```

## Fetch flow

1. `SubscriptionFetcher.fetch(url)` — HTTP GET with `User-Agent: v2rayN/6.0`.
2. Response body is tried as base64; if it contains `vless://` after decoding, the decoded text is used. Otherwise the raw body is used.
3. All `vless://` lines are extracted and passed to `parse_vless_list()`.
4. `storage.replace_subscription_proxies()` is called:
   - New URIs → inserted as `pending`
   - Existing URIs → status unchanged (dead ones reset to `pending`)
   - URIs removed from the subscription → marked `dead`
5. A health check cycle is triggered immediately for new/reset proxies.

## Polling

Each subscription runs in its own asyncio task (`_start_poller`):
- If `last_fetch` is `NULL` (startup or first run) → fetch immediately.
- If recently fetched → wait for the remaining interval.
- After each fetch, sleep `SUBSCRIPTION_FETCH_INTERVAL` seconds.

## URI deduplication

`raw_uri` (the database identity key) is built from the URI with query parameters sorted alphabetically and the fragment stripped. This ensures that the same server returned with different parameter order across fetches is recognised as the same proxy and does not create duplicate records.

## `SubscriptionManager`

| Method | Description |
|---|---|
| `startup()` | Register URLs from config in DB, start poller tasks |
| `refresh(sub_id)` | Fetch and apply one subscription immediately |
| `refresh_all()` | Fetch all subscriptions immediately |
| `shutdown()` | Cancel all poller tasks |
