# Архитектура

[English](../en/00-overview.md)

## Что делает сервис

Принимает VLESS-ссылки из трёх источников (Telegram-бот, файл `vless.txt`, REST API), валидирует их, проверяет живость через xray-core и держит пул рабочих SOCKS5-прокси на локальных портах.

## Компоненты

```
main.py
├── ProxyManager              — центральный оркестратор
│   ├── Storage               — SQLite база данных
│   ├── XrayProcessPool       — пул xray-процессов
│   ├── HealthChecker         — проверка живости
│   └── SubscriptionManager   — задачи поллинга подписок
├── FileWatcher               — наблюдает за vless.txt
├── FastAPI (uvicorn)         — REST API
└── Bot + Dispatcher          — Telegram-бот (aiogram 3)
```

## Жизненный цикл прокси

```
Входящие ссылки (бот / файл / API / подписка)
          │
          ▼
    parse_vless()              парсинг и валидация URI
          │
          ▼
  storage.replace_all()        сохранение в БД, статус → pending
  (или replace_subscription_proxies для подписок)
          │
          ▼
    HealthChecker              TCP-пинг + HTTP через временный xray
          │
     ┌────┴────┐
   жив        мёртв
     │          └──► если прокси подписки: проверить следующий
     ▼               pending из той же подписки
XrayProcessPool                запуск постоянного xray-процесса
     │
     ▼
socks5://127.0.0.1:<port>      доступно клиентам через API
```

## Статусы прокси в БД

| Статус    | Когда                                         |
|-----------|-----------------------------------------------|
| `pending` | Только добавлен, ещё не проверен              |
| `active`  | Жив, xray-процесс запущен                     |
| `dead`    | Не прошёл проверку; `fail_count` растёт       |

## Порты

- **10800–10820** — SOCKS5-порты пула (`PROXY_PORT_START` / `PROXY_PORT_END`)
- **19900–19999** — временные порты для health-check; не пересекаются с пулом

## Хранение состояния

Единственный источник правды — SQLite (`state.db`). `vless.txt` — временный входной канал: после загрузки удаляется. При перезапуске сервиса активные прокси восстанавливаются из БД и xray-процессы поднимаются снова.

## Стек

| Библиотека | Роль |
|---|---|
| pydantic-settings | Конфигурация через env/`.env` |
| aiosqlite | Асинхронный SQLite |
| aiohttp | HTTP-клиент в health-checker и fetcher подписок |
| FastAPI + uvicorn | REST API |
| aiogram 3 | Telegram-бот |
| xray-core | Внешний Go-бинарник; туннелирует трафик |

## Индекс модулей

| Файл | Документация |
|---|---|
| `config.py` | [Конфигурация](01-config.md) |
| `core/parser.py` | [Парсер VLESS ссылок](02-parser.md) |
| `core/storage.py` | [Хранилище (SQLite)](03-storage.md) |
| `core/xray.py` | [Управление xray-core](04-xray.md) |
| `core/health.py` | [Проверка живости](05-health.md) |
| `core/manager.py` | [Оркестратор](06-manager.md) |
| `api/server.py` | [REST API](07-api.md) |
| `bot/bot.py` | [Telegram-бот](08-bot.md) |
| `core/watcher.py` | [Файловый вотчер](09-watcher.md) |
| systemd | [Деплой](10-systemd.md) |
| `core/subscription.py` | [Подписки](11-subscription.md) |
