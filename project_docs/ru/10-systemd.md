# Деплой на Ubuntu (systemd)

[English](../en/10-systemd.md)

## Установка

```bash
cp scripts/vless-manager.service.example /etc/systemd/system/vless-manager.service
nano /etc/systemd/system/vless-manager.service   # прописать WorkingDirectory и User
sudo systemctl daemon-reload
sudo systemctl enable --now vless-manager
```

## Файл сервиса

```ini
[Unit]
Description=VLESS Proxy Manager
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/vless-proxy
EnvironmentFile=/root/vless-proxy/.env
ExecStart=/root/vless-proxy/.venv/bin/python main.py
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

Замените `WorkingDirectory`, `User` и `ExecStart` на актуальные значения.

## Основные команды

```bash
sudo systemctl start vless-manager      # запустить
sudo systemctl stop vless-manager       # остановить
sudo systemctl restart vless-manager    # перезапустить (после изменений кода/конфига)
sudo systemctl status vless-manager     # проверить статус
journalctl -u vless-manager -f          # следить за логами
journalctl -u vless-manager -n 100      # последние 100 строк логов
```

## Примечания

- `Restart=on-failure` — сервис автоматически перезапустится при падении.
- При каждом старте база прокси очищается и подписки загружаются заново.
- Бинарник xray должен быть установлен до запуска сервиса (`bash scripts/install-xray.sh`).
