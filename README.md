# VLESS Proxy Manager

Python service that accepts VLESS links, validates them, checks liveness through [xray-core](https://github.com/XTLS/Xray-core), and exposes active SOCKS5 proxies via REST API and Telegram bot.

## Quick start (local / macOS dev)

```bash
# 1. Install xray-core
bash scripts/install-xray.sh

# 2. Configure
cp .env.example .env
nano .env   # set TG_BOT_TOKEN and TG_ALLOWED_USER_IDS

# 3. Run
uv run python main.py
```

## Ubuntu server (systemd)

```bash
# 1. Clone and set up
git clone <repo> && cd vless-proxy
bash scripts/install-xray.sh
cp .env.example .env && nano .env
uv sync

# 2. Edit service file — replace /path/to/vless-proxy and YOUR_USERNAME
nano scripts/vless-manager.service
sudo cp scripts/vless-manager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vless-manager
```

## Configuration

All settings are loaded from environment variables or `.env`.

| Variable | Default | Description |
|---|---|---|
| `TG_BOT_TOKEN` | _(required)_ | Bot token from @BotFather |
| `TG_ALLOWED_USER_IDS` | _(required)_ | Comma-separated Telegram user IDs |
| `TG_NOTIFY_CHAT_ID` | _(empty)_ | Chat to send alive/dead notifications |
| `XRAY_BINARY` | `/usr/local/bin/xray` | Path to xray binary |
| `XRAY_CONFIG_DIR` | `/tmp/vless-manager` | Temp dir for xray config files |
| `PROXY_PORT_START` | `10800` | First SOCKS5 port in the pool |
| `PROXY_PORT_END` | `10820` | Last SOCKS5 port in the pool |
| `PROXY_BIND_HOST` | `127.0.0.1` | SOCKS5 bind address |
| `CHECK_URL` | `https://www.linkedin.com` | URL used to verify proxy works |
| `CHECK_TIMEOUT` | `10` | Seconds per health check |
| `CHECK_INTERVAL` | `300` | Seconds between full pool rechecks |
| `API_HOST` | `127.0.0.1` | REST API listen address |
| `API_PORT` | `8888` | REST API listen port |
| `API_SECRET_KEY` | _(empty)_ | Bearer token for `POST /update` (empty = disabled) |
| `DB_PATH` | `./state.db` | SQLite database path |
| `VLESS_FILE` | `./vless.txt` | File with VLESS links (watched for changes) |
| `FILE_CHECK_INTERVAL` | `30` | Seconds between file change polls |

## How to add proxies

**Via Telegram bot** — send VLESS links in a message or as a `.txt` file attachment.

**Via file** — edit `vless.txt` (or the path set in `VLESS_FILE`). The watcher picks up changes within `FILE_CHECK_INTERVAL` seconds. Lines starting with `#` are ignored.

```bash
# Quick update via script
echo "vless://..." | bash scripts/update-proxies.sh
```

**Via REST API** — requires `API_SECRET_KEY` to be set:

```bash
curl -X POST http://127.0.0.1:8888/update \
  -H "Authorization: Bearer YOUR_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{"links": ["vless://..."]}'
```

## REST API

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | — | Service liveness |
| GET | `/status` | — | Pool stats and uptime |
| GET | `/proxy/list` | — | All active proxies |
| GET | `/proxy/random` | — | Random active proxy |
| GET | `/proxy/best` | — | Lowest-latency proxy |
| POST | `/update` | Bearer | Submit new VLESS links |

### Client examples

**curl**

```bash
curl http://127.0.0.1:8888/proxy/best
```

**Python / httpx**

```python
import httpx

resp = httpx.get("http://127.0.0.1:8888/proxy/best").json()
proxy_url = f"socks5://127.0.0.1:{resp['local_port']}"

with httpx.Client(proxy=proxy_url) as client:
    print(client.get("https://example.com").status_code)
```

**aiohttp**

```python
import aiohttp

resp = await session.get("http://127.0.0.1:8888/proxy/best")
info = await resp.json()
proxy = f"socks5://127.0.0.1:{info['local_port']}"
```

## Service management (Ubuntu)

```bash
systemctl status vless-manager
systemctl restart vless-manager        # reload after .env changes
journalctl -u vless-manager -f         # live logs
journalctl -u vless-manager -p err     # errors only
journalctl -u vless-manager --since "1 hour ago"
```

## Project structure

```
├── main.py                # Entry point
├── config.py              # All settings (pydantic-settings)
├── .env.example           # Config reference
├── vless.txt.example      # VLESS links file format reference
├── core/
│   ├── parser.py          # VLESS URI parsing and validation
│   ├── storage.py         # SQLite persistence (aiosqlite)
│   ├── xray.py            # xray-core process management
│   ├── health.py          # SOCKS5 health checking
│   ├── manager.py         # Central orchestrator
│   └── watcher.py         # File-based proxy updates
├── api/
│   └── server.py          # FastAPI REST server
├── bot/
│   ├── bot.py             # Telegram bot (aiogram 3)
│   └── strings.py         # All user-facing text
└── scripts/
    ├── install-xray.sh        # xray-core binary installer
    ├── vless-manager.service  # systemd unit template
    └── update-proxies.sh      # CLI helper for updating vless.txt
```

## Troubleshooting

**xray not found**

```bash
bash scripts/install-xray.sh
which xray   # should print /usr/local/bin/xray
```

**No active proxies**

1. Check that your VLESS links are valid: `GET /proxy/list` (shows pending/dead too if any)
2. Watch health check logs: `journalctl -u vless-manager -f | grep health`
3. `CHECK_URL` must be reachable only through a proxy — if you're not in Russia, set it to a URL that's accessible to test connectivity, e.g. `https://httpbin.org/ip`

**Bot doesn't respond**

- Verify `TG_BOT_TOKEN` is correct
- Verify your Telegram user ID is in `TG_ALLOWED_USER_IDS`
- Check logs: `journalctl -u vless-manager -f | grep bot`

**Port conflicts**

- Change `PROXY_PORT_START` / `PROXY_PORT_END` if those ports are in use
- Health checks use a separate internal range (19900–19999) that doesn't overlap with the pool
