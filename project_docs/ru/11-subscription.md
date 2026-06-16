# Подписки (`core/subscription.py`)

[English](../en/11-subscription.md)

## Назначение

Подписки позволяют автоматически импортировать списки VLESS-прокси из внешних URL, без ручной передачи ссылок. Подписка — это URL, по которому отдаётся текстовый файл с `vless://`-ссылками (plain text или base64). Сервис скачивает его при старте и периодически, заменяя набор прокси подписки на свежий список.

## Ключевые принципы

- У каждой подписки свой набор прокси в БД (колонка `subscription_id`).
- Прокси подписок и прокси добавленные вручную **изолированы**: вызов `/update` или сообщение в боте никогда не удаляет прокси подписок, а обновление подписки не трогает ручные прокси.
- Когда прокси подписки умирает — менеджер автоматически берёт следующий `pending`-прокси **из той же подписки** и проверяет его. Ручного вмешательства не нужно.
- Каждая подписка запускает свою фоновую задачу поллинга.

## Формат ответа сервера подписки

Поддерживаются два формата:

**Plain text** — одна `vless://` ссылка на строку:
```
vless://uuid1@host1:443?security=tls&...#Name1
vless://uuid2@host2:443?security=tls&...#Name2
```

**Base64** — то же самое, закодированное в base64 (стандарт для большинства clash/v2ray серверов). Определяется автоматически: декодируем, проверяем наличие `vless://`; если нет — отдаём как есть.

При запросе используется `User-Agent: clash/1.18.0` для совместимости с большинством серверов подписок.

## Компоненты

### `SubscriptionFetcher`

Делает HTTP GET-запрос и декодирует тело ответа.

| Метод | Описание |
|---|---|
| `fetch(url) → FetchResult` | GET-запрос, декодирование, извлечение `vless://` ссылок |
| `_decode_body(body) → str` | Попытка base64-декодирования; fallback на plain text |

### `SubscriptionManager`

Оркестратор всех подписок. Создаётся `ProxyManager` при старте.

| Метод | Описание |
|---|---|
| `startup()` | Загружает подписки из БД, запускает задачи поллинга |
| `shutdown()` | Отменяет все задачи поллинга |
| `add_subscription(url, name, fetch_interval) → (id, FetchResult)` | Добавить подписку, сразу скачать, запустить поллер |
| `add_or_refresh(url) → FetchResult` | Добавить если новый, обновить если уже есть |
| `refresh_subscription(sub_id) → FetchResult` | Скачать и заменить прокси одной подписки |
| `refresh_all() → list[FetchResult]` | Обновить все подписки |
| `remove_subscription(sub_id)` | Отменить поллер, пометить прокси мёртвыми, удалить из БД |
| `get_subscription(sub_id)` | Получить строку подписки |
| `list_subscriptions()` | Список всех подписок со статистикой прокси |

### `FetchResult`

```python
@dataclass
class FetchResult:
    url: str
    success: bool
    links: list[str]   # сырые vless:// строки
    count: int         # количество валидных ссылок (после парсинга)
    error: str         # непустой при ошибке
```

## Схема БД

### Таблица `subscriptions`

| Колонка | Тип | Описание |
|---|---|---|
| `id` | INTEGER PK | Автоинкремент |
| `url` | TEXT UNIQUE | URL подписки |
| `name` | TEXT | Человекочитаемое название |
| `fetch_interval` | INTEGER | Интервал поллинга, сек (по умолчанию 3600) |
| `last_fetch` | REAL | Unix timestamp последнего успешного скачивания |
| `last_fetch_count` | INTEGER | Количество прокси в последнем успешном скачивании |
| `fail_count` | INTEGER | Количество ошибок подряд |

### Изменения в таблице `proxies`

Добавлены две колонки:

| Колонка | Описание |
|---|---|
| `source` | Откуда прокси: `'manual'`, `'file'`, `'telegram'`, `'api'`, или `'subscription:<id>'` |
| `subscription_id` | FK на `subscriptions.id`; `NULL` для ручных прокси |

Миграция выполняется автоматически при старте через `ALTER TABLE ... ADD COLUMN`.

## Жизненный цикл поллинга

```
startup()
  └── для каждой подписки в БД:
        _start_poller(sub)  →  asyncio.Task в self._tasks[sub_id]

задача поллера:
  цикл:
    sleep(оставшееся время до следующего скачивания)
    refresh_subscription(sub_id)
    обновить sub.fetch_interval, sub.last_fetch из БД
```

Начальный sleep рассчитывается как `fetch_interval - elapsed_since_last_fetch`. Если подписка никогда не скачивалась (`last_fetch = None`) — спит весь `fetch_interval`. Если интервал уже истёк — спит 0 (немедленно срабатывает).

## Замена мёртвых прокси

Когда прокси подписки объявляется мёртвым health-чекером, `ProxyManager._on_health_change` вызывает `_replace_dead_from_subscription`:

1. Проверяем `proxy.subscription_id`
2. Ищем `proxies WHERE subscription_id = sub_id AND status = 'pending' LIMIT 1`
3. Если нашли: запускаем `health_checker.check_one_by_id(candidate.id)` в фоне
4. Если нет: логируем и ждём следующего обновления подписки

Это поддерживает стабильное количество активных прокси без ожидания планового обновления.

## Конфигурация

| Переменная | По умолчанию | Описание |
|---|---|---|
| `SUBSCRIPTION_FETCH_INTERVAL` | `3600` | Интервал поллинга по умолчанию, сек |
| `SUBSCRIPTION_TIMEOUT` | `30` | Таймаут HTTP-запроса, сек |
| `SUBSCRIPTION_MAX_RETRIES` | `3` | Зарезервировано для логики повторов |

## Добавление через `vless.txt`

HTTP/HTTPS-строки в `vless.txt` воспринимаются как URL подписок:

```
# vless:// строки → ручные прокси
vless://uuid@host:443?...#Name

# http/https строки → URL подписок
https://sub.example.com/token123
```

При загрузке для каждой строки вызывается `add_or_refresh(url)` — добавляет если новый, обновляет если уже есть.

## Команды Telegram-бота

| Команда | Описание |
|---|---|
| `/sub_add <url> [название]` | Добавить подписку и сделать первое скачивание |
| `/sub_list` | Показать все подписки с количеством прокси |
| `/sub_refresh [id]` | Обновить одну подписку (или все, если id не указан) |
| `/sub_remove <id>` | Показать запрос подтверждения |
| `/sub_remove <id> confirm` | Удалить подписку и все её прокси |

## REST API

Все эндпоинты требуют `Authorization: Bearer <API_SECRET_KEY>`.

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/subscriptions` | Список всех подписок со статистикой |
| `POST` | `/subscriptions` | Добавить подписку |
| `DELETE` | `/subscriptions/{id}` | Удалить подписку и её прокси |
| `POST` | `/subscriptions/{id}/refresh` | Немедленное обновление |

### POST /subscriptions

```json
{
  "url": "https://sub.example.com/token",
  "name": "Мой провайдер",
  "fetch_interval": 3600
}
```

Ответ:
```json
{"id": 1, "url": "...", "name": "Мой провайдер", "fetched": 42}
```

### GET /subscriptions

Возвращает список объектов с полями:
- `id`, `url`, `name`, `fetch_interval`, `last_fetch`, `fail_count`
- `active`, `pending`, `dead`, `total` — количество прокси этой подписки
