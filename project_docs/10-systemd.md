# Модуль 10: точка входа и systemd

## Задача

Реализовать `main.py` — точку входа сервиса, и `vless-manager.service` — systemd unit для запуска на Ubuntu.

## `main.py`

Запускает все компоненты как asyncio задачи, обрабатывает сигналы.

```python
import asyncio
import logging
import signal
from config import settings
from core.storage import Storage
from core.manager import ProxyManager
from watcher.file_watcher import FileWatcher
from bot.bot import create_bot
from api.server import create_api_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

async def main():
    # 1. Инициализация
    storage = Storage(settings.DB_PATH)
    manager = ProxyManager(storage)
    await manager.startup()

    # 2. File watcher — загрузить файл при старте
    watcher = FileWatcher(manager)
    await watcher.load_once()

    # 3. Запустить все компоненты
    tasks = []

    # Health checker (внутри manager.startup уже запущен как task)

    # File watcher loop
    tasks.append(asyncio.create_task(watcher.run_forever(), name="file_watcher"))

    # REST API
    api_server = create_api_server(manager)
    tasks.append(asyncio.create_task(api_server.serve(), name="api_server"))

    # Telegram bot (только если токен задан)
    if settings.TG_BOT_TOKEN:
        bot, dp = create_bot(manager)
        tasks.append(asyncio.create_task(dp.start_polling(bot), name="telegram_bot"))
    else:
        logging.warning("TG_BOT_TOKEN not set, Telegram bot disabled")

    # 4. Обработка остановки
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def handle_signal():
        logging.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal)

    logging.info("VLESS Proxy Manager started")
    await stop_event.wait()

    # 5. Graceful shutdown
    logging.info("Shutting down...")
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await manager.shutdown()
    logging.info("Shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())
```

## `vless-manager.service`

```ini
[Unit]
Description=VLESS Proxy Manager
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=vless-manager
WorkingDirectory=/opt/vless-manager
EnvironmentFile=/opt/vless-manager/.env
ExecStart=/opt/vless-manager/.venv/bin/python main.py
Restart=on-failure
RestartSec=5
KillSignal=SIGTERM
TimeoutStopSec=15

# Логи через journald
StandardOutput=journal
StandardError=journal
SyslogIdentifier=vless-manager

[Install]
WantedBy=multi-user.target
```

## Скрипт установки `install.sh`

Создать `install.sh` который настраивает всё с нуля на чистой Ubuntu 22.04+:

```bash
#!/bin/bash
set -e

INSTALL_DIR="/opt/vless-manager"
SERVICE_USER="vless-manager"

echo "=== Installing VLESS Proxy Manager ==="

# 1. Создать пользователя
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /bin/false "$SERVICE_USER"
fi

# 2. Создать директорию
mkdir -p "$INSTALL_DIR"
cp -r . "$INSTALL_DIR/"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

# 3. Python venv
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# 4. xray-core
bash "$INSTALL_DIR/install-xray.sh"

# 5. .env
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    echo ""
    echo "⚠️  Настройте $INSTALL_DIR/.env перед запуском"
    echo "   Обязательно: TG_BOT_TOKEN, TG_ALLOWED_USER_IDS"
fi

# 6. systemd
cp "$INSTALL_DIR/vless-manager.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable vless-manager

echo ""
echo "✅ Установка завершена"
echo ""
echo "Следующие шаги:"
echo "  1. nano $INSTALL_DIR/.env          # задать токен бота"
echo "  2. systemctl start vless-manager   # запустить"
echo "  3. journalctl -u vless-manager -f  # смотреть логи"
```

## Просмотр логов

```bash
# Все логи
journalctl -u vless-manager -f

# Только ошибки
journalctl -u vless-manager -p err

# За последний час
journalctl -u vless-manager --since "1 hour ago"
```

## Команды управления

```bash
# Статус
systemctl status vless-manager

# Перезапуск (например после правки .env)
systemctl restart vless-manager

# Обновить ссылки через файл
nano /opt/vless-manager/vless.txt
# (watcher подхватит через 30 сек)

# Принудительная проверка через API
curl http://127.0.0.1:8888/status | python3 -m json.tool

# Получить прокси
curl http://127.0.0.1:8888/proxy/random
```

## README.md

Создать `README.md` с секциями:

1. Что это и зачем
2. Быстрый старт (3 команды)
3. Конфигурация (таблица всех переменных)
4. Как обновлять ссылки (бот / файл / API)
5. Примеры использования в клиентах (axios, aiogram, curl)
6. Структура проекта
7. Troubleshooting (xray не найден, нет живых прокси, бот не отвечает)
