# Проверка живости (`core/health.py`)

[English](../en/05-health.md)

## Как работает проверка

Каждый прокси проверяется в два этапа:

1. **TCP-пинг** — `check_proxy_tcp(host, port)` — просто пробует открыть соединение к серверу. Если нет даже TCP — сразу `dead`, xray не запускается.

2. **HTTP через xray** — `check_proxy(proxy_id, config)` — поднимает временный xray-процесс на порту `19900 + (proxy_id % 100)`, делает GET-запрос к `CHECK_URL` через этот SOCKS5-порт, смотрит на статус ответа.

После проверки временный xray-процесс останавливается и его конфиг-файл удаляется.

## Коды статусов — успех

```python
_SUCCESS_STATUSES = {200, 301, 302, 303, 307, 308, 403, 404, 429, 999}
```

Логика: если сервер отвечает любым кодом из этого набора — значит трафик прошёл через прокси, прокси живой. 403/404 от LinkedIn означает что запрос дошёл, просто заблокирован по какой-то причине. Таймаут или ошибка соединения = мёртвый прокси.

## `HealthResult`

```python
@dataclass
class HealthResult:
    proxy_id: int
    success: bool
    latency_ms: int | None    # только при success=True
    status_code: int | None
    error: str                 # описание ошибки при success=False
    checked_at: float          # unix timestamp
    check_url: str
```

## `HealthChecker`

Главный класс. Конкурентность ограничена семафором на 5 одновременных проверок.

```python
checker = HealthChecker(storage)
```

### Методы

**`check_one(proxy, config, on_status_change=None) → HealthResult`**

Проверяет один прокси, обновляет статус в БД, вызывает `on_status_change(result)` если передан.

**`check_pending(on_status_change=None) → list[HealthResult]`**

Проверяет все прокси со статусом `pending`. Вызывается сразу после добавления новых ссылок.

**`check_all_active(on_status_change=None) → list[HealthResult]`**

Проверяет все активные прокси. Плановая проверка — вдруг кто-то упал.

**`run_forever(on_status_change=None)`**

Бесконечный цикл: сначала active, потом pending, потом `sleep(CHECK_INTERVAL)`.

## Колбэк `on_status_change`

Синхронная функция `(HealthResult) → None`. Вызывается после каждой проверки. `HealthChecker` передаёт сюда результат; `ProxyManager` использует это чтобы запустить/остановить xray-процесс и отправить уведомление в Telegram.

Колбэк синхронный намеренно — `HealthChecker` не должен зависеть от логики менеджера. Менеджер внутри колбэка сам создаёт asyncio-задачу.

## Изоляция портов

Health-check использует порты `19900–19999` (формула: `19900 + proxy_id % 100`). Эти порты никогда не пересекаются с рабочим пулом (`10800–10820`), поэтому проверки не мешают работающим прокси.
