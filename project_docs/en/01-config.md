# Configuration (`config.py`)

[Русский](../ru/01-config.md)

## How it works

All settings live in a single pydantic model `Settings(BaseSettings)`. On module import a global `settings = Settings()` is created, reading values from environment variables and `.env` (if present).

```python
from config import settings

print(settings.API_PORT)       # 8888
print(settings.TG_BOT_TOKEN)   # "123456:ABC..."
```

## Variables

### Telegram

| Field | Type | Required | Default |
|-------|------|:---:|---|
| `TG_BOT_TOKEN` | `str` | ✓ | — |
| `TG_ALLOWED_USER_IDS` | `list[int]` | — | `[]` |
| `TG_NOTIFY_CHAT_ID` | `int \| None` | — | `None` |
| `TG_BOT_PROXY` | `str \| None` | — | `None` |

`TG_ALLOWED_USER_IDS` accepts a comma-separated string: `123,456,789`.

`TG_NOTIFY_CHAT_ID` — when set, the bot sends a message to this chat whenever a proxy changes status (alive / dead).

`TG_BOT_PROXY` — proxy for outgoing Telegram API requests. Use this on servers where Telegram is blocked. Supported schemes: `socks5://`, `socks4://`, `http://`. Typically points to one of the SOCKS5 ports in your own proxy pool:

```
TG_BOT_PROXY=socks5://127.0.0.1:10800
```

Requires the `aiohttp-socks` dependency. When not set, behaviour is unchanged.

### xray-core

| Field | Default | Description |
|-------|---|---|
| `XRAY_BINARY` | `/usr/local/bin/xray` | Path to the binary |
| `XRAY_CONFIG_DIR` | `/tmp/vless-manager` | Directory for temporary JSON configs |

### Proxy pool

| Field | Default | Description |
|-------|---|---|
| `PROXY_PORT_START` | `10800` | First SOCKS5 port |
| `PROXY_PORT_END` | `10820` | Last SOCKS5 port |
| `PROXY_BIND_HOST` | `127.0.0.1` | SOCKS5 bind address |

The range determines the maximum number of simultaneously running proxies (`END - START + 1`). With defaults — 21 proxies.

### Health check

| Field | Default | Description |
|-------|---|---|
| `CHECK_URL` | `https://www.linkedin.com` | URL to verify connectivity (must be blocked without a proxy) |
| `CHECK_TIMEOUT` | `10` | Single check timeout, seconds |
| `CHECK_INTERVAL` | `300` | Interval between full pool checks, seconds |
| `CHECK_STARTUP_XRAY_WAIT` | `2` | Pause after launching xray before the first request, seconds |

### REST API

| Field | Default | Description |
|-------|---|---|
| `API_HOST` | `127.0.0.1` | Listen address |
| `API_PORT` | `8888` | Port |
| `API_SECRET_KEY` | `""` | Bearer token for `POST /update`; empty = endpoint disabled |

Generate a key: `python3 -c "import secrets; print(secrets.token_hex(32))"`.

### Storage

| Field | Default | Description |
|-------|---|---|
| `DB_PATH` | `./state.db` | Path to the SQLite file |

### File watcher

| Field | Default | Description |
|-------|---|---|
| `VLESS_FILE` | `./vless.txt` | Links file path |
| `FILE_CHECK_INTERVAL` | `30` | File polling interval, seconds |

## Validation

`settings.validate()` is called manually at startup and checks:
- `TG_BOT_TOKEN` is not empty
- `XRAY_BINARY` exists (if not — warning only; service runs without xray in debug mode)
- `PROXY_PORT_START < PROXY_PORT_END`
