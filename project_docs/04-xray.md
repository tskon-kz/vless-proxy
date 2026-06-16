# Модуль 4: генерация xray конфигов и управление процессами

## Задача

Реализовать `core/xray.py` — генерация JSON-конфигов для xray-core и управление их жизненным циклом как subprocess.

## Что реализовать

### Функция `generate_xray_config(config: VlessConfig, local_port: int) -> dict`

Возвращает Python dict который потом сериализуется в JSON для xray. Структура конфига:

```json
{
  "log": { "loglevel": "warning" },
  "inbounds": [
    {
      "listen": "127.0.0.1",
      "port": <local_port>,
      "protocol": "socks",
      "settings": { "udp": true }
    }
  ],
  "outbounds": [
    {
      "protocol": "vless",
      "settings": {
        "vnext": [{
          "address": "<host>",
          "port": <port>,
          "users": [{
            "id": "<uuid>",
            "flow": "<flow>",
            "encryption": "none"
          }]
        }]
      },
      "streamSettings": <зависит от type и security>
    }
  ]
}
```

**`streamSettings` по типу транспорта (`config.type`):**

`tcp` с `security=reality`:
```json
{
  "network": "tcp",
  "security": "reality",
  "realitySettings": {
    "serverName": "<sni>",
    "fingerprint": "<fp>",
    "publicKey": "<pbk>",
    "shortId": "<sid>",
    "spiderX": "<spx>"
  }
}
```

`tcp` с `security=tls`:
```json
{
  "network": "tcp",
  "security": "tls",
  "tlsSettings": {
    "serverName": "<sni>",
    "fingerprint": "<fp>",
    "alpn": ["<alpn>"]   // если alpn не пустой
  }
}
```

`tcp` без security:
```json
{
  "network": "tcp",
  "tcpSettings": {
    "header": { "type": "<header_type>" }
  }
}
```

`ws`:
```json
{
  "network": "ws",
  "security": "<security>",
  "wsSettings": {
    "path": "<path>",
    "headers": { "Host": "<host_header>" }
  }
}
```
Добавить `tlsSettings` или `realitySettings` если security != none.

`grpc`:
```json
{
  "network": "grpc",
  "security": "<security>",
  "grpcSettings": {
    "serviceName": "<service_name>"
  }
}
```

### Функция `write_xray_config(config: VlessConfig, local_port: int, config_dir: str) -> str`

- Сгенерировать конфиг через `generate_xray_config`
- Записать в файл `<config_dir>/proxy_<local_port>.json`
- Создать директорию если не существует (`os.makedirs`)
- Вернуть путь к файлу

### Класс `XrayProcess`

Управляет одним запущенным xray процессом.

```python
class XrayProcess:
    def __init__(self, proxy_id: int, local_port: int, config_path: str):
        ...

    async def start(self) -> int:
        """Запустить xray, вернуть PID."""

    async def stop(self) -> None:
        """Остановить процесс (SIGTERM, таймаут 5с, потом SIGKILL)."""

    async def is_alive(self) -> bool:
        """Проверить что процесс запущен (os.kill(pid, 0))."""

    @property
    def pid(self) -> int | None:
        ...

    @property
    def local_port(self) -> int:
        ...
```

**Логика `start()`:**
1. `asyncio.create_subprocess_exec(settings.XRAY_BINARY, "run", "-config", config_path)`
2. stdout и stderr — `asyncio.subprocess.DEVNULL` (не захламлять логи)
3. Записать PID
4. Запустить задачу `_monitor()` в фоне

**Логика `_monitor()`:**
- Ждать завершения процесса через `await proc.wait()`
- Если процесс завершился — обновить статус в `Storage` на `crashed`
- Логировать через `logging`

**Логика `stop()`:**
- Отправить SIGTERM
- Ждать 5 секунд
- Если не завершился — SIGKILL
- Удалить config файл

### Класс `XrayProcessPool`

Управляет коллекцией `XrayProcess`.

```python
class XrayProcessPool:
    def __init__(self, storage: Storage):
        self._processes: dict[int, XrayProcess] = {}  # proxy_id -> XrayProcess

    async def start_proxy(self, proxy: ProxyRow, config: VlessConfig) -> XrayProcess | None:
        """Выделить порт, записать конфиг, запустить процесс, сохранить в storage."""

    async def stop_proxy(self, proxy_id: int) -> None:
        """Остановить и убрать из пула."""

    async def stop_all(self) -> None:
        """Остановить все процессы."""

    async def restart_proxy(self, proxy_id: int, config: VlessConfig) -> None:
        """stop + start."""

    def get_process(self, proxy_id: int) -> XrayProcess | None:
        ...

    def get_all_ports(self) -> dict[int, int]:
        """proxy_id -> local_port для всех running процессов."""
```

**Логика `start_proxy`:**
1. `storage.get_available_port()` — если нет свободных портов, логировать warning и вернуть None
2. `write_xray_config(config, port, settings.XRAY_CONFIG_DIR)`
3. `storage.upsert_process(proxy_id, port, config_path)`
4. Создать `XrayProcess`, вызвать `start()`
5. `storage.set_process_pid(proxy_id, pid, "running")`
6. Добавить в `self._processes`

## Важные детали

- `flow` в user конфиге: если пустая строка — не включать поле вообще (xray ругается на пустой flow)
- `alpn`: если непустой — массив строк, split по запятой
- Все операции с процессами — через asyncio, не threading
- Логировать старт/стоп каждого процесса с `proxy_id` и `local_port`
- При краше процесса — не перезапускать автоматически, это работа `Manager`

## Что НЕ нужно

- Парсить stdout xray — просто `/dev/null`
- Поддерживать несколько inbound на один процесс
- Health check в этом модуле — это отдельный модуль
