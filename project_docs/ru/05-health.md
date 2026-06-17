# Проверка живости (`core/health.py`)

[English](../en/05-health.md)

## Алгоритм проверки

Каждая проверка прокси проходит в два этапа:

1. **TCP ping** (`check_proxy_tcp`) — подключение к `host:port`. Быстрая и дешёвая проверка; сразу отсеивает недоступные серверы.
2. **HTTP-проверка** (`check_proxy`) — только если TCP успешен. Запускает временный процесс xray, отправляет HTTP-запрос к `CHECK_URL` через него, ожидает статус-код из `{200, 301, 302, 303, 307, 308, 403, 404, 429, 999}`. Измеряет задержку.

Прокси помечается **active** только при успехе HTTP-проверки. Неудача TCP сразу даёт статус **dead**.

## `HealthChecker`

| Метод | Описание |
|---|---|
| `check_one(proxy, config, on_status_change?)` | Проверить один прокси; обновить БД; вызвать callback при смене статуса |
| `check_pending(on_status_change?)` | Параллельно проверить все `pending` прокси |
| `check_all_active(on_status_change?)` | Параллельно проверить все `active` прокси |
| `check_dead(on_status_change?)` | Параллельно проверить все `dead` прокси |

## `HealthResult`

```python
@dataclass
class HealthResult:
    proxy_id: int
    success: bool
    latency_ms: int | None
    status_code: int | None
    error: str
    checked_at: float
    check_url: str
```

## Callback `on_status_change`

Вызывается после `check_one`, если статус прокси изменился. В `ProxyManager` этот callback запускает или останавливает процесс xray и отправляет Telegram-уведомление.

Callback срабатывает только при реальной смене статуса (`active → dead` или `dead/pending → active`). Первая проверка нового прокси (предыдущего статуса нет) уведомлений не генерирует.
