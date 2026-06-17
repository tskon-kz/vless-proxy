# Хранилище (`core/storage.py`)

[English](../en/03-storage.md)

SQLite через `aiosqlite`. Включён WAL-режим. Включены внешние ключи.

## Таблицы

### `proxies`

| Колонка | Тип | Описание |
|---|---|---|
| `id` | INTEGER PK | |
| `raw_uri` | TEXT UNIQUE | Канонический URI без фрагмента (ключ идентификации) |
| `uuid`, `host`, `port`, `name` | TEXT/INTEGER | Распарсенные поля |
| `security`, `type`, `flow` | TEXT | Параметры транспорта |
| `params_json` | TEXT | Полный `VlessConfig` сериализованный в JSON |
| `status` | TEXT | `pending` / `active` / `dead` |
| `last_check` | REAL | Unix timestamp последней проверки |
| `latency_ms` | INTEGER | Задержка последней успешной проверки |
| `fail_count` | INTEGER | Счётчик последовательных неудач |
| `subscription_id` | INTEGER | FK на `subscriptions` |

### `processes`

Отслеживает запущенные процессы xray. Одна запись на прокси, ключ — `local_port` (UNIQUE).

### `subscriptions`

| Колонка | Описание |
|---|---|
| `url` | URL подписки (UNIQUE) |
| `fetch_interval` | Интервал обновления, сек |
| `last_fetch` | Время последней успешной загрузки (NULL после рестарта) |
| `last_fetch_count` | Количество прокси в последней загрузке |
| `fail_count` | Счётчик последовательных ошибок загрузки |

## Ключевые методы

| Метод | Описание |
|---|---|
| `init()` | Создать таблицы, запустить миграции, **очистить прокси**, сбросить `last_fetch` |
| `upsert_proxy(config)` | Вставить или обновить прокси; возвращает `id`; статус при конфликте не меняется |
| `replace_subscription_proxies(sub_id, configs)` | Атомарно: новые URI → pending; исчезнувшие → dead |
| `set_proxy_status(id, status, latency_ms?)` | Обновить статус; active сбрасывает `fail_count`; dead увеличивает |
| `get_active_proxies()` | Все прокси со статусом `active` |
| `get_pending_proxies()` | Все прокси со статусом `pending` |
| `get_dead_proxies()` | Все прокси со статусом `dead` |
| `get_available_port()` | Наименьший свободный порт в диапазоне `PROXY_PORT_START..PROXY_PORT_END` |
| `get_stats()` | Возвращает `PoolStats(active, dead, pending, running_processes)` |

## Очистка при рестарте

`init()` выполняет `DELETE FROM proxies` и `UPDATE subscriptions SET last_fetch = NULL` при каждом старте. Это гарантирует, что база не накапливает устаревшие записи между перезапусками, а полеры подписок сразу делают первый фетч.
