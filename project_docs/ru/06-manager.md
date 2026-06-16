# Оркестратор (`core/manager.py`)

[English](../en/06-manager.md)

## Роль

`ProxyManager` — центральный компонент который связывает Storage, XrayProcessPool и HealthChecker. Все входные каналы (бот, файл, API) работают только через него.

## Инициализация

```python
storage = Storage(settings.DB_PATH)
manager = ProxyManager(storage)
await manager.startup()
```

`startup()`:
1. Инициализирует БД
2. Восстанавливает xray-процессы для всех `active` прокси из БД
3. Запускает проверку `pending` прокси в фоне
4. Запускает бесконечный цикл health-check (`run_forever`)

## Добавление прокси

```python
report = await manager.update_proxies(raw_links, source="telegram")
```

`update_proxies()` под `asyncio.Lock`:
1. Парсит ссылки через `parse_vless_list`
2. Вызывает `storage.replace_all` — сохраняет в БД, помечает исчезнувшие как `dead`
3. Останавливает xray-процессы для удалённых прокси
4. Запускает health-check для новых `pending` прокси в фоне

Возвращает `UpdateReport`:

```python
@dataclass
class UpdateReport:
    total_received: int   # len(raw_links) — все входящие строки
    valid: int            # успешно разобранные
    invalid: int          # total_received - valid
    parse_errors: list[str]
    newly_added: int      # новые (не были в БД)
    already_known: int    # обновлённые (уже были)
    removed: int          # помечены dead
    source: str           # "telegram" / "file" / "api"
```

## Реакция на смену статуса

Когда health-check завершает проверку, он вызывает синхронный колбэк `_status_change_callback`, который создаёт задачу `_on_health_change`:

```
прокси жив  → process_pool.start_proxy()   (если ещё не запущен)
прокси мёртв → process_pool.stop_proxy()  (если был запущен)
              → notify_callback(proxy, result)  (если настроен)
```

## Уведомления в Telegram

```python
manager.notify_callback: Callable[[ProxyRow, HealthResult], Awaitable[None]] | None
```

Устанавливается из `bot.py` если задан `TG_NOTIFY_CHAT_ID`. Принимает сырые данные — форматирование текста остаётся в `bot/strings.py`, менеджер не знает про Telegram.

## Получение прокси для клиента

```python
info = await manager.get_proxy_for_client()   # случайный активный
status = await manager.get_status()            # полный статус пула
```

`get_proxy_for_client()` перемешивает список активных и возвращает первый у которого есть работающий процесс.

## Фоновые задачи

Чтобы фоновые задачи не были потеряны GC (asyncio не держит слабые ссылки), менеджер хранит их в `_background_tasks: set[asyncio.Task]` и удаляет по завершении через `done_callback`.

При `shutdown()` все фоновые задачи отменяются, xray-процессы останавливаются, соединение с БД закрывается.
