# Deployment (systemd)

[Русский](../ru/10-systemd.md)

## Install

```bash
cp scripts/vless-manager.service.example /etc/systemd/system/vless-manager.service
nano /etc/systemd/system/vless-manager.service   # set WorkingDirectory and User
sudo systemctl daemon-reload
sudo systemctl enable --now vless-manager
```

## Service file

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

Adjust `WorkingDirectory`, `User`, and `ExecStart` to match your setup.

## Common commands

```bash
sudo systemctl start vless-manager      # start
sudo systemctl stop vless-manager       # stop
sudo systemctl restart vless-manager    # restart (after code/config changes)
sudo systemctl status vless-manager     # check status
journalctl -u vless-manager -f          # follow logs
journalctl -u vless-manager -n 100      # last 100 lines
```

## Notes

- The service uses `Restart=on-failure` — it will automatically restart if it crashes.
- On every start, the proxy DB is wiped and subscriptions are re-fetched from scratch.
- xray binary must be installed before starting the service (`bash scripts/install-xray.sh`).
