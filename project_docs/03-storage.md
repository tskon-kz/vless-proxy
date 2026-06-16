# Модуль 3: хранилище состояния (SQLite)

## Задача

Реализовать `core/storage.py` — асинхронное SQLite хранилище для состояния всего пула прокси. Единственный источник правды о том, какие серверы есть, живы ли они, на каком порту слушают.

## Что реализовать

### Схема БД

Три таблицы:

**`proxies`** — все известные VLESS серверы:
```sql
CREATE TABLE IF NOT EXISTS proxies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_uri     TEXT NOT NULL UNIQUE,
    uuid        TEXT NOT NULL,
    host        TEXT NOT NULL,
    port        INTEGER NOT NULL,
    name        TEXT DEFAULT '',
    security    TEXT DEFAULT 'none',
    type        TEXT DEFAULT 'tcp',
    flow        TEXT DEFAULT '',
    params_json TEXT DEFAULT '{}',   -- остальные параметры как JSON
    status      TEXT DEFAULT 'pending',  -- pending | active | dead | invalid
    last_check  REAL,                -- unix timestamp последней проверки
    latency_ms  INTEGER,             -- задержка последней успешной проверки
    fail_count  INTEGER DEFAULT 0,   -- сколько раз подряд упала проверка
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
```

**`processes`** — запущенные xray процессы:
```sql
CREATE TABLE IF NOT EXISTS processes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    proxy_id    INTEGER NOT NULL REFERENCES proxies(id) ON DELETE CASCADE,
    local_port  INTEGER NOT NULL UNIQUE,
    pid         INTEGER,             -- NULL если процесс не запущен
    config_path TEXT NOT NULL,       -- путь к временному xray конфигу
    started_at  REAL,
    status      TEXT DEFAULT 'stopped'  -- running | stopped | crashed
);
```

**`update_log`** — история обновлений списка ссылок:
```sql
CREATE TABLE IF NOT EXISTS update_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,  -- telegram | file | api
    total       INTEGER,
    valid       INTEGER,
    invalid     INTEGER,
    added       INTEGER,
    removed     INTEGER,
    created_at  REAL NOT NULL
);
```

### Класс `Storage`

Асинхронный. Использует `aiosqlite`. Пул соединений не нужен — одно соединение на весь lifetime сервиса.

**Методы:**

```python
async def init() -> None
```
Создать таблицы если не существуют. Вызывается один раз при старте.

```python
async def upsert_proxy(config: VlessConfig) -> int
```
Добавить новый прокси или обновить существующий по `raw_uri`. Вернуть `id`. При вставке статус `pending`, при апдейте — не трогать статус.

```python
async def set_proxy_status(proxy_id: int, status: str, latency_ms: int | None = None) -> None
```
Обновить статус и `last_check`. Если статус `active` — сбросить `fail_count` в 0. Если `dead` — инкрементировать `fail_count`.

```python
async def get_active_proxies() -> list[ProxyRow]
```
Все прокси со статусом `active`.

```python
async def get_pending_proxies() -> list[ProxyRow]
```
Все прокси со статусом `pending` (ждут проверки).

```python
async def get_all_proxies() -> list[ProxyRow]
```
Все прокси любого статуса.

```python
async def replace_all(configs: list[VlessConfig], source: str) -> UpdateStats
```
Атомарно заменить весь список прокси. В транзакции:
1. Получить текущий список `raw_uri`
2. Вставить/обновить все новые
3. Прокси которых нет в новом списке — пометить статусом `dead` (не удалять, для истории)
4. Записать в `update_log`
5. Вернуть `UpdateStats(total, valid, added, removed)`

```python
async def get_process(proxy_id: int) -> ProcessRow | None
async def upsert_process(proxy_id: int, local_port: int, config_path: str) -> None
async def set_process_pid(proxy_id: int, pid: int | None, status: str) -> None
async def get_available_port() -> int | None
```
`get_available_port` — найти свободный порт из диапазона `settings.PROXY_PORT_START..PROXY_PORT_END`, который не занят в таблице `processes`.

```python
async def log_update(source: str, stats: UpdateStats) -> None
async def get_stats() -> PoolStats
```
`get_stats` — агрегат: сколько active/dead/pending/invalid, сколько процессов running.

```python
async def close() -> None
```
Закрыть соединение с БД.

### Датаклассы результатов

```python
@dataclass
class ProxyRow:
    id: int
    raw_uri: str
    host: str
    port: int
    name: str
    security: str
    type: str
    flow: str
    params: dict      # десериализованный params_json
    status: str
    last_check: float | None
    latency_ms: int | None
    fail_count: int

@dataclass
class ProcessRow:
    id: int
    proxy_id: int
    local_port: int
    pid: int | None
    config_path: str
    status: str

@dataclass
class UpdateStats:
    total: int
    valid: int
    invalid: int
    added: int
    removed: int

@dataclass
class PoolStats:
    active: int
    dead: int
    pending: int
    invalid: int
    running_processes: int
```

## Важные детали

- Все методы — `async def`, используют `await`
- `Storage` должен быть инстансом, не набором статик-методов — его передают через dependency injection в другие модули
- Соединение открывается в `init()`, закрывается в `close()`
- `replace_all` обёрнут в `BEGIN TRANSACTION / COMMIT` — если что-то падает, откат
- Timestamps — `time.time()` (unix float), не datetime объекты
- `params_json` — сериализовать через `json.dumps(asdict(config))` со всеми параметрами VlessConfig

## Что НЕ нужно

- Миграции — сервис молодой, достаточно `CREATE TABLE IF NOT EXISTS`
- ORM (SQLAlchemy и др.) — только чистый aiosqlite с f-строками запросов
- Кеширование результатов запросов
