# VLESS Proxy Manager

A service that manages a pool of VLESS proxies via subscriptions: fetches server lists, checks liveness via xray-core, and exposes working SOCKS5 proxies through a REST API and Telegram bot.

[Русская версия](README_RU.md)

## Quick Start

### Local (macOS / Linux)

```bash
bash scripts/install-xray.sh
cp .env.example .env
nano .env          # required: TG_BOT_TOKEN, TG_ALLOWED_USER_IDS, SUBSCRIPTION_URLS
uv sync
uv run python main.py
```

### Ubuntu server (systemd)

```bash
git clone <repo> && cd vless-proxy
bash scripts/install-xray.sh
cp .env.example .env && nano .env
uv sync

cp scripts/vless-manager.service.example /etc/systemd/system/vless-manager.service
nano /etc/systemd/system/vless-manager.service   # adjust WorkingDirectory and User
sudo systemctl daemon-reload
sudo systemctl enable --now vless-manager
```

```bash
journalctl -u vless-manager -f          # logs
sudo systemctl restart vless-manager    # restart after code/config changes
```

## Configuration (.env)

| Variable | Default | Description |
|---|---|---|
| `TG_BOT_TOKEN` | — | Bot token from @BotFather **(required)** |
| `TG_ALLOWED_USER_IDS` | `[]` | JSON array of allowed Telegram user IDs **(required)** |
| `TG_NOTIFY_CHAT_ID` | — | Chat ID for status change notifications |
| `TG_BOT_PROXY` | — | SOCKS5 proxy for Telegram API |
| `SUBSCRIPTION_URLS` | `[]` | JSON array of subscription URLs **(required)** |
| `SUBSCRIPTION_FETCH_INTERVAL` | `1800` | Seconds between subscription refreshes |
| `SUBSCRIPTION_TIMEOUT` | `30` | Fetch timeout, seconds |
| `XRAY_BINARY` | `/usr/local/bin/xray` | Path to xray binary |
| `XRAY_CONFIG_DIR` | `/tmp/vless-manager` | Temp directory for xray configs |
| `PROXY_PORT_START` | `10800` | First SOCKS5 port |
| `PROXY_PORT_END` | `10820` | Last SOCKS5 port |
| `PROXY_BIND_HOST` | `127.0.0.1` | SOCKS5 bind address |
| `CHECK_URL` | `https://www.linkedin.com` | URL used to verify proxy (should be blocked without proxy) |
| `CHECK_TIMEOUT` | `10` | Single check timeout, seconds |
| `CHECK_INTERVAL` | `300` | Health check cycle interval, seconds |
| `API_HOST` | `127.0.0.1` | REST API bind address |
| `API_PORT` | `8888` | REST API port |
| `DB_PATH` | `./state.db` | SQLite database path |

`SUBSCRIPTION_URLS` must be a JSON array:
```env
SUBSCRIPTION_URLS=["https://sub.example.com/token"]
SUBSCRIPTION_URLS=["https://sub1.example.com/token","https://sub2.example.com/token"]
```

## REST API

| Method | Path | Description |
|---|---|---|
| GET | `/proxy/best` | Fastest proxy (lowest latency) |
| GET | `/proxy/list` | All active proxies as a plain array |

```bash
curl http://127.0.0.1:8888/proxy/best
# {"url": "socks5://127.0.0.1:10800"}

curl http://127.0.0.1:8888/proxy/list
# ["socks5://127.0.0.1:10800", "socks5://127.0.0.1:10801"]
```

```python
import httpx

url = httpx.get("http://127.0.0.1:8888/proxy/best").json()["url"]
with httpx.Client(proxy=url) as client:
    print(client.get("https://example.com").status_code)
```

## Telegram Bot

| Command | Description |
|---|---|
| `/status` | Pool stats and list of active proxies |
| `/check` | Force recheck all servers |
| `/help` | Help |

If `TG_NOTIFY_CHAT_ID` is set, the bot sends a message when a proxy goes dead or comes back online during operation (no notifications on startup).

## How It Works

1. On every startup, the proxy DB is wiped and subscriptions are fetched immediately.
2. Each subscription is refreshed every `SUBSCRIPTION_FETCH_INTERVAL` seconds (default 30 min).
3. After each fetch, new proxies are health-checked; removed proxies are marked dead.
4. Active proxies each run a persistent xray process on a SOCKS5 port.
5. The fastest proxy (lowest latency) is always reordered to `PROXY_PORT_START`.
6. Health checks run every `CHECK_INTERVAL` seconds; dead proxies are rechecked every 3rd cycle.

## Documentation

- [Architecture overview](project_docs/en/00-overview.md)
- [Configuration](project_docs/en/01-config.md)
- [VLESS parser](project_docs/en/02-parser.md)
- [Storage (SQLite)](project_docs/en/03-storage.md)
- [xray-core management](project_docs/en/04-xray.md)
- [Health checker](project_docs/en/05-health.md)
- [Manager (orchestrator)](project_docs/en/06-manager.md)
- [REST API](project_docs/en/07-api.md)
- [Telegram bot](project_docs/en/08-bot.md)
- [Subscriptions](project_docs/en/11-subscription.md)
- [Deployment (systemd)](project_docs/en/10-systemd.md)
