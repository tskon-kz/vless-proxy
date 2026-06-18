# VLESS Proxy Manager
[English version](README.md)

## Что умеет

**Прокси сервис:**
- Загружает VLESS-серверы из одной или нескольких подписок (base64 URL)
- Проверяет живость каждого сервера через xray-core (TCP ping + HTTP)
- Поднимает пул рабочих SOCKS5-прокси на локальных портах (по умолчанию 10800–10820)
- Сортирует прокси по задержке — самый быстрый всегда на первом порту
- Периодически перепроверяет серверы и автоматически заменяет упавшие
- Хранит состояние в SQLite; при перезапуске сразу обновляет подписки
- Деплоится как systemd-сервис на Ubuntu

**REST API (`http://127.0.0.1:8888`):**
- `GET /proxy/best` — возвращает самый быстрый прокси (`socks5://127.0.0.1:10800`)
- `GET /proxy/list` — список всех активных прокси

**Telegram-бот:**
- `/status` — статистика пула и список активных прокси
- `/check` — принудительная проверка всех серверов
- Уведомления в чат при смене статуса прокси

**Можно использовать:**
- Для TG-ботов на `aiogram` / `python-telegram-bot` — библиотеки поддерживают `socks5://`
- Для любых HTTP-клиентов на Python (`httpx`, `requests`) — передать URL прокси из `/proxy/best`
- Для обхода блокировок из CI/скриптов — опросить API и подставить прокси в команду
- Как прозрачный прокси-пул: сервис сам следит за живостью и переключает порты

## Быстрый старт

### Локально (macOS / Linux)

```bash
bash scripts/install-xray.sh
cp .env.example .env
nano .env          # обязательно: TG_BOT_TOKEN, TG_ALLOWED_USER_IDS, SUBSCRIPTION_URLS
uv sync
uv run python main.py
```

### Ubuntu-сервер (systemd)

```bash
git clone <repo> && cd vless-proxy
bash scripts/install-xray.sh
cp .env.example .env && nano .env
uv sync

cp scripts/vless-manager.service.example /etc/systemd/system/vless-manager.service
nano /etc/systemd/system/vless-manager.service   # прописать WorkingDirectory и User
sudo systemctl daemon-reload
sudo systemctl enable --now vless-manager
```

```bash
journalctl -u vless-manager -f          # логи
sudo systemctl restart vless-manager    # перезапуск после изменений кода/конфига
```

## Настройки (.env)

| Переменная | По умолчанию | Описание |
|---|---|---|
| `TG_BOT_TOKEN` | — | Токен бота от @BotFather **(обязательно)** |
| `TG_ALLOWED_USER_IDS` | `[]` | JSON-массив Telegram user ID **(обязательно)** |
| `TG_NOTIFY_CHAT_ID` | — | ID чата для уведомлений о смене статуса |
| `TG_BOT_PROXY` | — | SOCKS5-прокси для подключения к Telegram API |
| `SUBSCRIPTION_URLS` | `[]` | JSON-массив URL подписок **(обязательно)** |
| `SUBSCRIPTION_FETCH_INTERVAL` | `1800` | Интервал обновления подписок, сек |
| `SUBSCRIPTION_TIMEOUT` | `30` | Таймаут загрузки подписки, сек |
| `XRAY_BINARY` | `/usr/local/bin/xray` | Путь к бинарнику xray |
| `XRAY_CONFIG_DIR` | `/tmp/vless-manager` | Временная директория для конфигов xray |
| `PROXY_PORT_START` | `10800` | Первый SOCKS5-порт |
| `PROXY_PORT_END` | `10820` | Последний SOCKS5-порт |
| `PROXY_BIND_HOST` | `127.0.0.1` | Адрес прослушивания SOCKS5 |
| `CHECK_URL` | `https://www.linkedin.com` | URL для проверки живости (должен быть заблокирован без прокси) |
| `CHECK_TIMEOUT` | `10` | Таймаут одной проверки, сек |
| `CHECK_INTERVAL` | `300` | Интервал между циклами проверок, сек |
| `API_HOST` | `127.0.0.1` | Адрес REST API |
| `API_PORT` | `8888` | Порт REST API |
| `DB_PATH` | `./state.db` | Путь к SQLite базе данных |

`SUBSCRIPTION_URLS` задаётся в формате JSON-массива:
```env
SUBSCRIPTION_URLS=["https://sub.example.com/token"]
SUBSCRIPTION_URLS=["https://sub1.example.com/token","https://sub2.example.com/token"]
```

## REST API

| Метод | Путь | Описание |
|---|---|---|
| GET | `/proxy/best` | Самый быстрый прокси (минимальная задержка) |
| GET | `/proxy/list` | Все активные прокси в виде массива |

```bash
curl http://127.0.0.1:8888/proxy/best
# {"url": "socks5://127.0.0.1:10800"}

curl http://127.0.0.1:8888/proxy/list
# ["socks5://127.0.0.1:10800", "socks5://127.0.0.1:10801"]
```

```python
import httpx

url = httpx.get("http://127.0.0.1:8888/proxy/best").json()["url"]
with httpx.Client(proxy=url) as client:
    print(client.get("https://example.com").status_code)
```

## Telegram-бот

| Команда | Описание |
|---|---|
| `/status` | Статистика пула и список активных прокси |
| `/check` | Принудительная проверка всех серверов |
| `/help` | Справка |

Если задан `TG_NOTIFY_CHAT_ID`, бот отправляет сообщение при смене статуса прокси в процессе работы (при старте уведомления не отправляются).

## Как это работает

1. При каждом запуске база прокси очищается, подписки загружаются немедленно.
2. Каждая подписка обновляется раз в `SUBSCRIPTION_FETCH_INTERVAL` секунд (по умолчанию 30 мин).
3. После обновления новые прокси проверяются на живость; пропавшие помечаются мёртвыми.
4. Для каждого активного прокси запускается постоянный процесс xray на отдельном SOCKS5-порту.
5. Самый быстрый прокси (минимальная задержка) всегда занимает `PROXY_PORT_START`.
6. Проверки идут каждые `CHECK_INTERVAL` секунд; мёртвые перепроверяются раз в 3 цикла.

## Подробная документация

- [Архитектура и обзор](project_docs/ru/00-overview.md)
- [Конфигурация](project_docs/ru/01-config.md)
- [Парсер VLESS](project_docs/ru/02-parser.md)
- [Хранилище (SQLite)](project_docs/ru/03-storage.md)
- [Управление xray-core](project_docs/ru/04-xray.md)
- [Проверка живости](project_docs/ru/05-health.md)
- [Менеджер (оркестратор)](project_docs/ru/06-manager.md)
- [REST API](project_docs/ru/07-api.md)
- [Telegram-бот](project_docs/ru/08-bot.md)
- [Подписки](project_docs/ru/11-subscription.md)
- [Деплой (systemd)](project_docs/ru/10-systemd.md)
