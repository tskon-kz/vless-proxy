# Хранилище (`core/storage.py`)

## Обзор

Тонкая обёртка над SQLite через aiosqlite. Все методы асинхронные. БД инициализируется вызовом `await storage.init()`.

```python
storage = Storage("./state.db")
await storage.init()
```

## Схема БД

### `proxies`

Основная таблица. Одна строка = один VLESS-сервер.

| Колонка | Тип | Описание |
|---------|-----|----------|
| `id` | INTEGER PK | Авто-инкремент |
| `raw_uri` | TEXT UNIQUE | Исходная строка ссылки — уникальный ключ |
| `uuid`, `host`, `port` | TEXT/INT | Быстрые поля для запросов |
| `name`, `security`, `type`, `flow` | TEXT | Параметры соединения |
| `params_json` | TEXT | Полный `VlessConfig` сериализованный в JSON |
| `status` | TEXT | `pending` / `active` / `dead` |
| `last_check` | REAL | Unix-timestamp последней проверки |
| `latency_ms` | INTEGER | Задержка при последней успешной проверке |
| `fail_count` | INTEGER | Счётчик последовательных неудач |

### `processes`

Запущенные xray-процессы. Один процесс = один активный прокси.

| Колонка | Описание |
|---------|----------|
| `proxy_id` | FK → proxies.id |
| `local_port` | UNIQUE — занятый локальный порт |
| `pid` | PID процесса xray (NULL если не запущен) |
| `config_path` | Путь к JSON-конфигу xray |
| `status` | `stopped` / `running` / `crashed` |

### `update_log`

Журнал обновлений пула. Пишется при каждом вызове `replace_all`.

## Ключевые методы

### `upsert_proxy(config) → int`

Вставляет новый прокси или обновляет метаданные существующего (по `raw_uri`). **Статус при конфликте не меняется** — если прокси был `active`, он останется `active`.

Возвращает `id` записи.

### `replace_all(configs, source) → UpdateStats`

Атомарная операция обновления всего пула:

1. Все ссылки из `configs` — upsert (статус не трогается при конфликте)
2. Всё что было в БД со статусом ≠ `dead`, но не вошло в `configs` — помечается `dead`
3. В `update_log` пишется запись с источником и статистикой

Выполняется в транзакции — при ошибке откат (`rollback`).

### `set_proxy_status(proxy_id, status, latency_ms)`

Обновляет статус прокси:
- `active` → сбрасывает `fail_count = 0`, пишет `latency_ms`
- `dead` → увеличивает `fail_count + 1`, обнуляет `latency_ms`

### `get_available_port() → int | None`

Возвращает первый свободный порт из диапазона `PROXY_PORT_START..PROXY_PORT_END`. Порт считается занятым если есть запись в `processes` со статусом `running`.

### `get_stats() → PoolStats`

Возвращает агрегированные счётчики: active, dead, pending, invalid, running_processes.

## Датаклассы

```python
@dataclass
class ProxyRow:
    id: int; raw_uri: str; host: str; port: int; name: str
    security: str; type: str; flow: str; params: dict
    status: str; last_check: float | None
    latency_ms: int | None; fail_count: int

@dataclass
class ProcessRow:
    id: int; proxy_id: int; local_port: int
    pid: int | None; config_path: str; status: str

@dataclass
class PoolStats:
    active: int; dead: int; pending: int; invalid: int
    running_processes: int
```

## Настройки БД

При инициализации включаются:
- `PRAGMA journal_mode=WAL` — Write-Ahead Logging, позволяет параллельные чтения
- `PRAGMA foreign_keys=ON` — каскадное удаление процессов при удалении прокси
