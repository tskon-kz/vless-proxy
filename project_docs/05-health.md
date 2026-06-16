# Модуль 5: проверка живости серверов (Health Checker)

## Задача

Реализовать `core/health.py` — проверка доступности VLESS серверов через попытку обращения к заблокированному в РФ ресурсу. Живой сервер = тот, через который `CHECK_URL` из конфига отвечает успешно.

## Логика проверки

### Почему именно заблокированный ресурс

Обычный TCP ping или curl на `example.com` не показывает работоспособность прокси: сервер может быть доступен, но сам заблокирован провайдером или попал под санкции. Проверка через `linkedin.com` (или другой `CHECK_URL`) гарантирует: если ответ пришёл — прокси реально работает и обходит блокировки.

### Алгоритм проверки одного сервера

1. Запустить временный xray процесс на случайном свободном порту из диапазона (или фиксированный `CHECK_PORT = 19999`)
2. Подождать `settings.CHECK_STARTUP_XRAY_WAIT` секунд — xray нужно время инициализироваться
3. Сделать HTTP GET запрос через SOCKS5 прокси на `127.0.0.1:CHECK_PORT` к `settings.CHECK_URL`
4. Проверить ответ
5. Остановить и удалить временный xray процесс
6. Вернуть результат

### Что считать успехом

HTTP статус коды которые означают "сервер живой":
- `200` — OK
- `999` — LinkedIn возвращает 999 для bot-like запросов, но это значит ресурс доступен
- `301`, `302`, `303`, `307`, `308` — редиректы, ресурс есть
- `403`, `404`, `429` — тоже OK, главное что соединение установлено

Провал:
- `aiohttp.ClientError` любого рода (connection refused, timeout, proxy error)
- Таймаут превысил `settings.CHECK_TIMEOUT`
- xray процесс упал до завершения запроса

## Что реализовать

### Датакласс `HealthResult`

```python
@dataclass
class HealthResult:
    proxy_id: int
    success: bool
    latency_ms: int | None    # время от начала запроса до первого байта ответа
    status_code: int | None   # HTTP статус или None при ошибке
    error: str                # описание ошибки или "" если успех
    checked_at: float         # unix timestamp
    check_url: str            # какой URL проверяли (из конфига на момент проверки)
```

### Функция `check_proxy(proxy_id: int, vless_config: VlessConfig) -> HealthResult`

Основная функция. Async.

**Детали реализации:**

Запуск временного xray:
```python
# Использовать фиксированный порт для проверки
CHECK_PORT = 19999  # или брать из settings
config_path = write_xray_config(vless_config, CHECK_PORT, settings.XRAY_CONFIG_DIR + "/health")
proc = await asyncio.create_subprocess_exec(
    settings.XRAY_BINARY, "run", "-config", config_path,
    stdout=asyncio.subprocess.DEVNULL,
    stderr=asyncio.subprocess.DEVNULL
)
await asyncio.sleep(settings.CHECK_STARTUP_XRAY_WAIT)
```

HTTP запрос через SOCKS5:
```python
connector = aiohttp.TCPConnector()
async with aiohttp.ClientSession(connector=connector) as session:
    async with session.get(
        settings.CHECK_URL,
        proxy=f"socks5://127.0.0.1:{CHECK_PORT}",
        timeout=aiohttp.ClientTimeout(total=settings.CHECK_TIMEOUT),
        allow_redirects=False,   # не следовать редиректам — они тоже успех
        headers={"User-Agent": "Mozilla/5.0"}  # минимальный UA чтобы не блокировали сразу
    ) as resp:
        status = resp.status
```

Замер latency — через `time.monotonic()` вокруг блока запроса.

Cleanup — всегда в `finally`: `proc.terminate()`, удалить config файл.

Обработка параллельных проверок — `CHECK_PORT` должен быть уникальным если несколько проверок идут параллельно. Решение: использовать asyncio Lock или генерировать порт как `19900 + (proxy_id % 100)`.

### Функция `check_proxy_tcp(host: str, port: int) -> bool`

Быстрая предварительная проверка — просто TCP connect. Не запускает xray.

```python
async def check_proxy_tcp(host: str, port: int, timeout: float = 5.0) -> bool:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout
        )
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False
```

Используется как первый фильтр: если TCP недоступен — не тратить время на полную проверку.

### Класс `HealthChecker`

```python
class HealthChecker:
    def __init__(self, storage: Storage):
        self._storage = storage
        self._semaphore = asyncio.Semaphore(5)  # максимум 5 параллельных проверок

    async def check_one(self, proxy: ProxyRow, config: VlessConfig) -> HealthResult:
        """Проверить один прокси, обновить статус в storage."""

    async def check_all_active(self) -> list[HealthResult]:
        """Проверить все active прокси параллельно (с семафором)."""

    async def check_pending(self) -> list[HealthResult]:
        """Проверить все pending прокси — новые, ещё не проверенные."""

    async def run_forever(self, on_status_change: Callable | None = None) -> None:
        """Бесконечный цикл проверок с интервалом settings.CHECK_INTERVAL."""
```

**Логика `check_one`:**
1. TCP check — если упал, сразу `storage.set_proxy_status(id, "dead")`
2. Полная проверка через xray
3. Если успех: `storage.set_proxy_status(id, "active", latency_ms)`
4. Если провал: `storage.set_proxy_status(id, "dead")`
5. Если `fail_count >= 3` и статус был `active` — логировать что сервер похоже умер окончательно
6. Вызвать `on_status_change(result)` callback если задан

**Логика `run_forever`:**
```python
while True:
    await self.check_all_active()
    await self.check_pending()
    await asyncio.sleep(settings.CHECK_INTERVAL)
```

**Логика `check_all_active` (параллельно с семафором):**
```python
async def _check_with_semaphore(proxy, config):
    async with self._semaphore:
        return await self.check_one(proxy, config)

tasks = [_check_with_semaphore(p, c) for p, c in proxy_config_pairs]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

## Важные детали

- Порты для health check не пересекаются с пулом прокси (`10800-10820`) — использовать диапазон `19900-19999`
- Каждый check_one создаёт и удаляет свой temp xray процесс — не переиспользовать
- `allow_redirects=False` важен — иначе aiohttp будет следовать редиректам и может зависнуть
- Логировать каждую проверку: proxy_id, host, результат, latency — это основной отладочный инструмент
- Если `settings.XRAY_BINARY` не существует — `check_one` сразу возвращает ошибку с понятным сообщением, не крашится

## Что НЕ нужно

- Кешировать результаты проверок
- Retry логику внутри check_one — Manager решает когда перепроверять
- WebRTC/STUN/DNS leak test — только HTTP через SOCKS5
