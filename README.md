# VLESS Proxy Manager

A service that manages a pool of VLESS proxies: accepts links, checks liveness via xray-core, and exposes working SOCKS5 proxies through a REST API and Telegram bot.

[Русская версия](README_RU.md)

## Quick Start

### Local development (macOS / Linux)

```bash
# 1. Install xray-core
bash scripts/install-xray.sh

# 2. Configure
cp .env.example .env
nano .env   # required: TG_BOT_TOKEN, TG_ALLOWED_USER_IDS

# 3. Install dependencies and run
uv sync
uv run python main.py
```

### Ubuntu server (systemd)

```bash
# 1. Clone the repository
git clone <repo> && cd vless-proxy

# 2. Install xray-core and dependencies
bash scripts/install-xray.sh
cp .env.example .env && nano .env
uv sync

# 3. Edit the service file — replace /path/to/vless-proxy and YOUR_USERNAME
nano scripts/vless-manager.service
sudo cp scripts/vless-manager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vless-manager
```

View logs:
```bash
journalctl -u vless-manager -f
```

## Configuration (.env)

| Variable | Default | Description |
|---|---|---|
| `TG_BOT_TOKEN` | — | Bot token from @BotFather (required) |
| `TG_ALLOWED_USER_IDS` | — | Comma-separated Telegram user IDs (required) |
| `TG_NOTIFY_CHAT_ID` | — | Chat to receive proxy alive/dead notifications |
| `XRAY_BINARY` | `/usr/local/bin/xray` | Path to xray binary |
| `XRAY_CONFIG_DIR` | `/tmp/vless-manager` | Temp directory for xray configs |
| `PROXY_PORT_START` | `10800` | First port in the SOCKS5 pool |
| `PROXY_PORT_END` | `10820` | Last port in the SOCKS5 pool |
| `PROXY_BIND_HOST` | `127.0.0.1` | SOCKS5 bind address |
| `CHECK_URL` | `https://www.linkedin.com` | URL to verify proxy (should be blocked without proxy) |
| `CHECK_TIMEOUT` | `10` | Single check timeout, seconds |
| `CHECK_INTERVAL` | `300` | Interval between scheduled pool checks, seconds |
| `API_HOST` | `127.0.0.1` | REST API bind address |
| `API_PORT` | `8888` | REST API port |
| `API_SECRET_KEY` | — | Bearer token for `POST /update` (empty = endpoint disabled) |
| `DB_PATH` | `./state.db` | SQLite database path |
| `VLESS_FILE` | `./vless.txt` | File with VLESS links for auto-loading |
| `FILE_CHECK_INTERVAL` | `30` | File change polling interval, seconds |

## How to Add Proxies

**Via Telegram bot** — send `vless://` links as text or attach a `.txt` file.

**Via subscription** — `/sub_add https://sub.example.com/token [name]`. The service fetches the URL immediately and then polls it every `SUBSCRIPTION_FETCH_INTERVAL` seconds (default 1 hour). Subscription proxies are isolated from manual updates.

**Via file** — create `vless.txt` with links (one per line, `#` for comments). HTTP/HTTPS lines are treated as subscription URLs. The service loads the file on startup and deletes it. Dropping a file while running — picked up within `FILE_CHECK_INTERVAL` seconds.

**Via REST API:**
```bash
curl -X POST http://127.0.0.1:8888/update \
  -H "Authorization: Bearer YOUR_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{"links": ["vless://..."]}'
```

## REST API

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | — | Service liveness check |
| GET | `/status` | — | Pool stats and active proxy list |
| GET | `/proxy/list` | — | All active proxies |
| GET | `/proxy/random` | — | Random active proxy |
| GET | `/proxy/best` | — | Lowest-latency proxy |
| POST | `/update` | Bearer | Submit new VLESS links |
| GET | `/subscriptions` | Bearer | List subscriptions with proxy counts |
| POST | `/subscriptions` | Bearer | Add subscription |
| DELETE | `/subscriptions/{id}` | Bearer | Remove subscription and its proxies |
| POST | `/subscriptions/{id}/refresh` | Bearer | Trigger immediate refresh |

Using a proxy from the API response:
```python
import httpx

info = httpx.get("http://127.0.0.1:8888/proxy/best").json()
# info["proxy_url"] == "socks5://127.0.0.1:10800"

with httpx.Client(proxy=info["proxy_url"]) as client:
    print(client.get("https://example.com").status_code)
```

### External access

By default both the API and SOCKS5 ports listen on `127.0.0.1` only. To expose them to other machines:

```env
API_HOST=0.0.0.0          # API reachable from outside
PROXY_BIND_HOST=1.2.3.4   # use the server's real public IP, not 0.0.0.0
```

Setting `PROXY_BIND_HOST` to the real IP is important: the API embeds it into `proxy_url` in every response (`socks5://<PROXY_BIND_HOST>:<port>`), so clients receive a URL they can actually connect to.

> **Security note:** GET endpoints (`/proxy/list`, `/status`, etc.) have no authentication — anyone who can reach the API can see your proxy list. Restrict access via a firewall, or put the API behind a reverse proxy with auth.
> `POST /update` is protected by `API_SECRET_KEY` (or hidden entirely when the key is not set).

## Documentation

- [Architecture overview](project_docs/en/00-overview.md)
- [Configuration](project_docs/en/01-config.md)
- [VLESS link parser](project_docs/en/02-parser.md)
- [Storage (SQLite)](project_docs/en/03-storage.md)
- [xray-core management](project_docs/en/04-xray.md)
- [Health checker](project_docs/en/05-health.md)
- [Orchestrator](project_docs/en/06-manager.md)
- [REST API](project_docs/en/07-api.md)
- [Telegram bot](project_docs/en/08-bot.md)
- [File watcher](project_docs/en/09-watcher.md)
- [Deployment (systemd)](project_docs/en/10-systemd.md)
- [Subscriptions](project_docs/en/11-subscription.md)
