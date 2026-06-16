# Архитектура

## Что делает сервис

Принимает VLESS-ссылки из трёх источников (Telegram-бот, файл `vless.txt`, REST API), валидирует их, проверяет живость через xray-core и держит пул рабочих SOCKS5-прокси на локальных портах.

## Компоненты

```
main.py
├── ProxyManager          — центральный оркестратор
│   ├── Storage           — SQLite база данных
│   ├── XrayProcessPool   — пул xray-процессов
│   └── HealthChecker     — проверка живости
├── FileWatcher           — наблюдает за vless.txt
├── FastAPI (uvicorn)     — REST API
└── Bot + Dispatcher      — Telegram-бот (aiogram 3)
```

## Жизненный цикл прокси

```
Входящие ссылки (бот / файл / API)
          │
          ▼
    parse_vless()              парсинг и валидация URI
          │
          ▼
  storage.replace_all()        сохранение в БД, статус → pending
          │
          ▼
    HealthChecker              TCP-пинг + HTTP через временный xray
          │
     ┌────┴────┐
   жив        мёртв
     │
     ▼
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
| aiohttp | HTTP-клиент в health-checker |
| FastAPI + uvicorn | REST API |
| aiogram 3 | Telegram-бот |
| xray-core | Внешний Go-бинарник; туннелирует трафик |
