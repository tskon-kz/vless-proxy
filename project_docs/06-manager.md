# Модуль 6: оркестратор (Core Manager)

## Задача

Реализовать `core/manager.py` — центральный компонент, который связывает все остальные модули. Принимает новые ссылки, запускает/останавливает xray процессы, реагирует на результаты health check.

## Что реализовать

### Класс `ProxyManager`

Синглтон. Все остальные компоненты (бот, file watcher, API) общаются с сервисом только через него.

```python
class ProxyManager:
    def __init__(self, storage: Storage):
        self.storage = storage
        self.process_pool = XrayProcessPool(storage)
        self.health_checker = HealthChecker(storage)
        self._lock = asyncio.Lock()   # для update_proxies
```

### Метод `startup() -> None`

Вызывается при старте сервиса. Порядок:
1. `storage.init()` — создать таблицы
2. Восстановить состояние из БД: взять все `active` прокси, запустить для них xray процессы
3. Запустить `health_checker.check_pending()` — проверить всё что было `pending` до перезапуска
4. Запустить `health_checker.run_forever(on_status_change=self._on_health_change)` как asyncio Task
5. Логировать сколько прокси восстановлено

### Метод `shutdown() -> None`

Вызывается при остановке сервиса (SIGTERM/SIGINT):
1. Отменить task health checker
2. `process_pool.stop_all()`
3. `storage.close()`

### Метод `update_proxies(raw_links: list[str], source: str) -> UpdateReport`

Основной метод обновления. Вызывается из бота и file watcher. Защищён `asyncio.Lock` — нельзя запускать параллельно.

```python
@dataclass
class UpdateReport:
    total_received: int
    valid: int
    invalid: int
    parse_errors: list[str]    # описания ошибок парсинга для отчёта
    newly_added: int
    already_known: int
    removed: int               # сколько убрано из активных (были в старом списке, нет в новом)
    source: str
```

**Алгоритм:**

```
1. parse_vless_list(raw_links) → valid_configs, all_results
2. storage.replace_all(valid_configs, source) → UpdateStats
3. Для каждого нового прокси (status=pending):
   a. Запустить health check (не ждать — в фоне через asyncio.create_task)
4. Для прокси которые убраны из списка (status сменился на dead):
   a. process_pool.stop_proxy(proxy_id)
5. Вернуть UpdateReport
```

Важно: health check новых прокси запускается в фоне, `update_proxies` не блокируется на это.

### Метод `_on_health_change(result: HealthResult) -> None`

Callback который вызывает health checker при изменении статуса.

```python
async def _on_health_change(self, result: HealthResult) -> None:
    proxy = await self.storage.get_proxy_by_id(result.proxy_id)

    if result.success and proxy.status != "active":
        # сервер ожил — запустить xray процесс
        config = parse_vless(proxy.raw_uri).config
        await self.process_pool.start_proxy(proxy, config)

    elif not result.success and proxy.status == "active":
        # сервер умер — остановить процесс
        await self.process_pool.stop_proxy(result.proxy_id)
```

### Метод `get_status() -> ManagerStatus`

Агрегированный статус для API и бота.

```python
@dataclass
class ManagerStatus:
    pool_stats: PoolStats          # из storage.get_stats()
    active_proxies: list[ProxyInfo]  # список живых с портами и latency
    check_url: str                 # текущий CHECK_URL из конфига
    uptime_seconds: float

@dataclass
class ProxyInfo:
    proxy_id: int
    name: str
    host: str
    port: int
    local_port: int
    latency_ms: int | None
    last_check: float | None
```

### Метод `force_recheck() -> None`

Немедленно запустить проверку всех прокси (не ждать следующего интервала). Вызывается из бота по команде `/check`.

```python
async def force_recheck(self) -> None:
    asyncio.create_task(self._run_full_check())

async def _run_full_check(self) -> None:
    await self.health_checker.check_all_active()
    await self.health_checker.check_pending()
```

### Метод `get_proxy_for_client() -> ProxyInfo | None`

Вернуть один случайный живой прокси. Используется в REST API для `/proxy/random`.

```python
async def get_proxy_for_client(self) -> ProxyInfo | None:
    active = await self.storage.get_active_proxies()
    if not active:
        return None
    proxy = random.choice(active)
    process = await self.storage.get_process(proxy.id)
    if not process or process.status != "running":
        return None
    return ProxyInfo(...)
```

## Инициализация и DI

`ProxyManager` создаётся один раз в `main.py` и передаётся во все компоненты:

```python
# main.py
storage = Storage(settings.DB_PATH)
manager = ProxyManager(storage)

# передать в бот
bot_app = create_bot(manager)

# передать в API
api_app = create_api(manager)

# передать в file watcher
watcher = FileWatcher(manager)
```

## Обработка ошибок

- Если xray бинарник не найден при старте — логировать critical, но не падать. Прокси будут в статусе `pending` пока xray не появится.
- Если нет свободных портов — логировать warning, новые прокси не запускать
- Если `update_proxies` вызвана пока предыдущая ещё выполняется — ждать на Lock, не отклонять

## Что НЕ нужно

- Retry логики здесь — это в health checker
- Персистентность очереди задач — всё в памяти, при рестарте восстанавливаемся из БД
