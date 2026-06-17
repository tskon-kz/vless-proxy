# Конфигурация (`config.py`)

[English](../en/01-config.md)

Все настройки читаются из `.env` через pydantic-settings. Файл подхватывается автоматически.

## Обязательные настройки

| Переменная | Описание |
|---|---|
| `TG_BOT_TOKEN` | Токен бота от @BotFather |
| `TG_ALLOWED_USER_IDS` | JSON-массив Telegram user ID |
| `SUBSCRIPTION_URLS` | JSON-массив URL подписок |

`TG_ALLOWED_USER_IDS` и `SUBSCRIPTION_URLS` должны быть валидными JSON-массивами:
```env
TG_ALLOWED_USER_IDS=[221061944]
SUBSCRIPTION_URLS=["https://sub.example.com/token"]
```

## Все настройки

| Переменная | По умолчанию | Описание |
|---|---|---|
| `TG_BOT_TOKEN` | — | Токен Telegram-бота |
| `TG_ALLOWED_USER_IDS` | `[]` | Разрешённые Telegram user ID |
| `TG_NOTIFY_CHAT_ID` | `None` | ID чата для уведомлений о смене статуса прокси |
| `TG_BOT_PROXY` | `None` | SOCKS5-прокси для Telegram API (если Telegram заблокирован на сервере) |
| `SUBSCRIPTION_URLS` | `[]` | URL подписок для опроса |
| `SUBSCRIPTION_FETCH_INTERVAL` | `1800` | Интервал обновления подписок, сек |
| `SUBSCRIPTION_TIMEOUT` | `30` | Таймаут загрузки подписки, сек |
| `XRAY_BINARY` | `/usr/local/bin/xray` | Путь к бинарнику xray |
| `XRAY_CONFIG_DIR` | `/tmp/vless-manager` | Директория для временных конфигов xray |
| `PROXY_PORT_START` | `10800` | Первый SOCKS5-порт |
| `PROXY_PORT_END` | `10820` | Последний SOCKS5-порт (размер пула = END − START + 1) |
| `PROXY_BIND_HOST` | `127.0.0.1` | Адрес прослушивания SOCKS5 |
| `CHECK_URL` | `https://www.linkedin.com` | URL для проверки живости (выбирайте сайт, заблокированный без прокси) |
| `CHECK_TIMEOUT` | `10` | Таймаут одной проверки, сек |
| `CHECK_INTERVAL` | `300` | Интервал между циклами проверок, сек |
| `CHECK_STARTUP_XRAY_WAIT` | `2` | Ожидание перед HTTP-запросом после старта xray, сек |
| `API_HOST` | `127.0.0.1` | Адрес REST API |
| `API_PORT` | `8888` | Порт REST API |
| `DB_PATH` | `./state.db` | Путь к SQLite базе |

## Размер пула

Максимальное число одновременно активных прокси ограничено диапазоном портов: `PROXY_PORT_END - PROXY_PORT_START + 1`. По умолчанию 51 (10800–10850). В подписках может быть больше серверов — лишние остаются в статусе `pending` или `dead` до освобождения порта.
