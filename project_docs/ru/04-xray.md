# Управление xray-core (`core/xray.py`)

[English](../en/04-xray.md)

## Обзор

Модуль делает две вещи:
1. Генерирует JSON-конфиги для xray-core по параметрам VLESS
2. Управляет дочерними процессами xray (`XrayProcess`, `XrayProcessPool`)

## Генерация конфигов

### `generate_xray_config(config, local_port) → dict`

Создаёт конфиг xray в формате JSON. Структура:

```json
{
  "log": { "loglevel": "warning" },
  "inbounds": [{
    "listen": "127.0.0.1",
    "port": 10800,
    "protocol": "socks",
    "settings": { "udp": true }
  }],
  "outbounds": [{
    "protocol": "vless",
    "settings": { "vnext": [{ "address": "...", "port": 443, "users": [...] }] },
    "streamSettings": { ... }
  }]
}
```

Поле `flow` добавляется в `users` только если оно не пустое — xray отклоняет пустую строку.

### `write_xray_config(config, local_port, config_dir) → str`

Записывает конфиг в файл `<config_dir>/proxy_<local_port>.json`. Создаёт директорию если отсутствует. Возвращает путь к файлу.

### Поддерживаемые транспорты

| transport | security | Что генерируется |
|-----------|----------|------------------|
| `tcp` | `reality` | `realitySettings` |
| `tcp` | `tls` | `tlsSettings` |
| `tcp` | `none` | `tcpSettings` с `headerType` |
| `ws` | any | `wsSettings` + опционально tls/reality |
| `grpc` | any | `grpcSettings` + опционально tls/reality |

## Управление процессами

### `XrayProcess`

Обёртка над одним дочерним процессом xray.

```python
proc = XrayProcess(proxy_id, local_port, config_path, storage)
pid = await proc.start()    # запуск, возвращает PID
await proc.stop()           # SIGTERM → 5 сек → SIGKILL; удаляет config файл
alive = await proc.is_alive()
```

При запуске автоматически создаётся фоновая задача `_monitor()` которая ждёт завершения процесса и при неожиданном выходе обновляет статус в БД на `crashed`.

### `XrayProcessPool`

Хранит все запущенные процессы в словаре `{proxy_id: XrayProcess}`.

```python
pool = XrayProcessPool(storage)

proc = await pool.start_proxy(proxy_id, config)
# 1. Берёт свободный порт из БД
# 2. Записывает конфиг xray на диск
# 3. Создаёт XrayProcess и запускает его
# 4. Сохраняет PID в БД

await pool.stop_proxy(proxy_id)
await pool.restart_proxy(proxy_id, new_config)
await pool.stop_all()

ports = pool.get_all_ports()  # {proxy_id: local_port}
```

Если свободных портов нет — `start_proxy` возвращает `None` и логирует предупреждение.
