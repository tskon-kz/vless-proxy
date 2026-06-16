# Deployment (systemd)

[Русский](../ru/10-systemd.md)

## Requirements

- Ubuntu 22.04+
- Python 3.11+
- [uv](https://github.com/astral-sh/uv)

## Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Steps

### 1. Clone the repository

```bash
git clone <repo> /opt/vless-proxy
cd /opt/vless-proxy
```

### 2. Install xray-core

```bash
bash scripts/install-xray.sh
which xray   # should print /usr/local/bin/xray
```

### 3. Configure

```bash
cp .env.example .env
nano .env
```

Required fields:
- `TG_BOT_TOKEN` — token from @BotFather
- `TG_ALLOWED_USER_IDS` — your Telegram user ID

Get your ID from @userinfobot.

Generate `API_SECRET_KEY` if the API endpoint is needed:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 4. Install dependencies

```bash
uv sync
```

### 5. Configure the systemd service

The repository contains a template. Copy it and fill in the real values:

```bash
cp scripts/vless-manager.service.example scripts/vless-manager.service
nano scripts/vless-manager.service
```

Replace:
- `/path/to/vless-proxy` → actual path (e.g. `/opt/vless-proxy`)
- `YOUR_USERNAME` → the user to run the service as

The edited file is listed in `.gitignore`, so it will not appear in `git status`.

```bash
sudo cp scripts/vless-manager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable vless-manager
```

### 6. Start

```bash
sudo systemctl start vless-manager
sudo systemctl status vless-manager
```

## Service management

```bash
# Status
systemctl status vless-manager

# Restart (e.g. after editing .env)
systemctl restart vless-manager

# Stop
systemctl stop vless-manager

# Live logs
journalctl -u vless-manager -f

# Errors only
journalctl -u vless-manager -p err

# Logs from the last hour
journalctl -u vless-manager --since "1 hour ago"
```

## Updating the code

```bash
cd /opt/vless-proxy
git pull
uv sync
systemctl restart vless-manager
```

## Service file template (`scripts/vless-manager.service.example`)

```ini
[Unit]
Description=VLESS Proxy Manager
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/path/to/vless-proxy
EnvironmentFile=/path/to/vless-proxy/.env
ExecStart=/path/to/vless-proxy/.venv/bin/python main.py
Restart=on-failure
RestartSec=5
KillSignal=SIGTERM
TimeoutStopSec=15
StandardOutput=journal
StandardError=journal
SyslogIdentifier=vless-manager

[Install]
WantedBy=multi-user.target
```

`ExecStart` uses the Python from the `.venv` virtual environment created by `uv sync`. The path must be absolute — systemd does not support relative paths in `ExecStart`.
