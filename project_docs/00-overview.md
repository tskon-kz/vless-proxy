# VLESS Proxy Manager — обзор проекта

## Что это

Python-сервис на Ubuntu. Принимает список VLESS-ссылок, валидирует их, проверяет живость через подключение к заблокированному в РФ ресурсу, запускает xray-core процессы для каждого живого сервера, отдаёт пул актуальных SOCKS5-прокси через REST API.

## Модули (порядок реализации)

1. `01-config.md` — конфиг и структура проекта
2. `02-parser.md` — парсер и валидатор VLESS URI
3. `03-storage.md` — SQLite хранилище состояния
4. `04-xray.md` — генерация xray конфигов + управление процессами
5. `05-health.md` — проверка живости серверов
6. `06-manager.md` — оркестратор: lifecycle всего пула
7. `07-api.md` — REST API для клиентов (axios, aiogram и др.)
8. `08-bot.md` — Telegram бот
9. `09-file-watcher.md` — файловый fallback для обновления ссылок
10. `10-systemd.md` — установка как systemd-сервис

## Стек

- Python 3.11+
- aiogram 3.x (Telegram бот)
- FastAPI + uvicorn (REST API)
- aiosqlite (хранилище)
- aiohttp (health check запросы)
- xray-core (внешний бинарник, Go)

## Структура репозитория

```
vless-proxy-manager/
├── config.py
├── main.py
├── requirements.txt
├── install-xray.sh
├── vless-manager.service
├── vless.txt                  # fallback файл со ссылками
├── core/
│   ├── __init__.py
│   ├── parser.py
│   ├── storage.py
│   ├── xray.py
│   ├── health.py
│   └── manager.py
├── api/
│   ├── __init__.py
│   └── server.py
├── bot/
│   ├── __init__.py
│   └── bot.py
└── watcher/
    ├── __init__.py
    └── file_watcher.py
```

## Архитектура работы

```
[Telegram Bot] ──┐
                 ├──> [Core Manager] ──> [Parser] ──> [Health Check] ──> [xray processes]
[File Watcher] ──┘                                                              │
                                                                                ▼
[REST API] <──────────────────────────────────────────── [SOCKS5 Pool :10800+]
     │
     ▼
[axios / aiogram / curl]
```

## Принцип проверки живости

Для каждой VLESS-ссылки поднимается временный xray-процесс и через него делается HTTP GET на `CHECK_URL` из конфига (по умолчанию `https://www.linkedin.com`). Этот ресурс заблокирован в РФ — если запрос проходит через прокси и возвращает 200/999, сервер работает и не заблокирован. Если нет — сервер мёртв или тоже заблокирован.

## Два способа обновления списка ссылок

1. **Telegram бот** — основной, интерактивный, с отчётом о результатах
2. **Файловый watcher** — fallback: кладёшь `vless.txt` в директорию сервиса, сервис подхватывает автоматически. Работает даже если Telegram недоступен.

## Code style
Комментарии все на английском.
Русский текст, например для бота - держать в отдельных языковых файлах.