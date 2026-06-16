# Деплой на Ubuntu (systemd)

[English](../en/10-systemd.md)

## Требования

- Ubuntu 22.04+
- Python 3.11+
- [uv](https://github.com/astral-sh/uv)

## Установка uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Шаги

### 1. Клонировать репозиторий

```bash
git clone <repo> /opt/vless-proxy
cd /opt/vless-proxy
```

### 2. Установить xray-core

```bash
bash scripts/install-xray.sh
which xray   # должно вернуть /usr/local/bin/xray
```

### 3. Настроить окружение

```bash
cp .env.example .env
nano .env
```

Обязательно заполнить:
- `TG_BOT_TOKEN` — токен от @BotFather
- `TG_ALLOWED_USER_IDS` — ваш Telegram ID

Получить свой ID можно у бота @userinfobot.

Сгенерировать `API_SECRET_KEY` если нужен API:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 4. Установить зависимости

```bash
uv sync
```

### 5. Настроить systemd-службу

Открыть `scripts/vless-manager.service` и заменить:
- `/path/to/vless-proxy` → реальный путь (например `/opt/vless-proxy`)
- `YOUR_USERNAME` → имя пользователя от которого запускать

```bash
nano scripts/vless-manager.service
sudo cp scripts/vless-manager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable vless-manager
```

### 6. Запустить

```bash
sudo systemctl start vless-manager
sudo systemctl status vless-manager
```

## Управление службой

```bash
# Статус
systemctl status vless-manager

# Перезапуск (например после правки .env)
systemctl restart vless-manager

# Остановка
systemctl stop vless-manager

# Логи в реальном времени
journalctl -u vless-manager -f

# Только ошибки
journalctl -u vless-manager -p err

# Логи за последний час
journalctl -u vless-manager --since "1 hour ago"
```

## Обновление кода

```bash
cd /opt/vless-proxy
git pull
uv sync
systemctl restart vless-manager
```

## Файл службы (`scripts/vless-manager.service`)

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

`ExecStart` использует Python из виртуального окружения `.venv`, созданного командой `uv sync`. Путь абсолютный — systemd не поддерживает относительные пути в `ExecStart`.
