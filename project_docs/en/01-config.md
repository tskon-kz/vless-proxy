# Configuration (`config.py`)

[Русский](../ru/01-config.md)

All settings are read from `.env` via pydantic-settings. The file is loaded automatically; no explicit path is needed.

## Required settings

| Variable | Description |
|---|---|
| `TG_BOT_TOKEN` | Bot token from @BotFather |
| `TG_ALLOWED_USER_IDS` | JSON array of Telegram user IDs allowed to use the bot |
| `SUBSCRIPTION_URLS` | JSON array of subscription URLs |

`TG_ALLOWED_USER_IDS` and `SUBSCRIPTION_URLS` must be valid JSON arrays:
```env
TG_ALLOWED_USER_IDS=[221061944]
SUBSCRIPTION_URLS=["https://sub.example.com/token"]
```

## All settings

| Variable | Default | Description |
|---|---|---|
| `TG_BOT_TOKEN` | — | Telegram bot token |
| `TG_ALLOWED_USER_IDS` | `[]` | Allowed Telegram user IDs |
| `TG_NOTIFY_CHAT_ID` | `None` | Chat ID for proxy status notifications |
| `TG_BOT_PROXY` | `None` | SOCKS5 proxy for Telegram API (useful if Telegram is blocked on the server) |
| `SUBSCRIPTION_URLS` | `[]` | Subscription URLs to poll |
| `SUBSCRIPTION_FETCH_INTERVAL` | `1800` | Seconds between subscription refreshes |
| `SUBSCRIPTION_TIMEOUT` | `30` | Subscription fetch timeout, seconds |
| `XRAY_BINARY` | `/usr/local/bin/xray` | Path to xray binary |
| `XRAY_CONFIG_DIR` | `/tmp/vless-manager` | Directory for temporary xray config files |
| `PROXY_PORT_START` | `10800` | First SOCKS5 port |
| `PROXY_PORT_END` | `10820` | Last SOCKS5 port (max pool size = END − START + 1) |
| `PROXY_BIND_HOST` | `127.0.0.1` | SOCKS5 bind address |
| `CHECK_URL` | `https://www.linkedin.com` | URL used to verify proxy (pick a site blocked without proxy) |
| `CHECK_TIMEOUT` | `10` | Single check timeout, seconds |
| `CHECK_INTERVAL` | `300` | Seconds between health check cycles |
| `CHECK_STARTUP_XRAY_WAIT` | `2` | Seconds to wait for xray to start before sending HTTP request |
| `API_HOST` | `127.0.0.1` | REST API bind address |
| `API_PORT` | `8888` | REST API port |
| `DB_PATH` | `./state.db` | SQLite database path |

## Pool size

The number of simultaneously active proxies is limited by the port range: `PROXY_PORT_END - PROXY_PORT_START + 1`. Default is 51 (10800–10850). Subscriptions can have more servers — extras stay as `pending` or `dead` until a slot opens.
