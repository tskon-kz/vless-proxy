# VLESS Proxy Manager

Сервис для управления пулом VLESS прокси: принимает ссылки, проверяет живость через xray-core и отдаёт рабочие SOCKS5 прокси через REST API и Telegram-бота.

## Быстрый старт

### Локальная разработка (macOS / Linux)

```bash
# 1. Установить xray-core
bash scripts/install-xray.sh

# 2. Настроить окружение
cp .env.example .env
nano .env   # обязательно: TG_BOT_TOKEN, TG_ALLOWED_USER_IDS

# 3. Установить зависимости и запустить
uv sync
uv run python main.py
```

### Ubuntu-сервер (systemd)

```bash
# 1. Клонировать репозиторий
git clone <repo> && cd vless-proxy

# 2. Установить xray-core и зависимости
bash scripts/install-xray.sh
cp .env.example .env && nano .env
uv sync

# 3. Настроить и запустить службу
#    Открыть scripts/vless-manager.service,
#    заменить /path/to/vless-proxy и YOUR_USERNAME на реальные значения
nano scripts/vless-manager.service
sudo cp scripts/vless-manager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vless-manager
```

Логи:
```bash
journalctl -u vless-manager -f
```

## Настройки (.env)

| Переменная | По умолчанию | Описание |
|---|---|---|
| `TG_BOT_TOKEN` | — | Токен бота от @BotFather (обязательно) |
| `TG_ALLOWED_USER_IDS` | — | Telegram ID через запятую (обязательно) |
| `TG_NOTIFY_CHAT_ID` | — | Куда слать уведомления о смене статуса прокси |
| `XRAY_BINARY` | `/usr/local/bin/xray` | Путь к бинарнику xray |
| `XRAY_CONFIG_DIR` | `/tmp/vless-manager` | Временные конфиги xray |
| `PROXY_PORT_START` | `10800` | Начало диапазона SOCKS5 портов |
| `PROXY_PORT_END` | `10820` | Конец диапазона SOCKS5 портов |
| `PROXY_BIND_HOST` | `127.0.0.1` | Адрес прослушивания SOCKS5 |
| `CHECK_URL` | `https://www.linkedin.com` | URL для проверки живости (должен быть заблокирован без прокси) |
| `CHECK_TIMEOUT` | `10` | Таймаут одной проверки, сек |
| `CHECK_INTERVAL` | `300` | Интервал между плановыми проверками, сек |
| `API_HOST` | `127.0.0.1` | Адрес REST API |
| `API_PORT` | `8888` | Порт REST API |
| `API_SECRET_KEY` | — | Bearer-токен для `POST /update` (пусто = эндпоинт отключён) |
| `DB_PATH` | `./state.db` | Путь к SQLite базе данных |
| `VLESS_FILE` | `./vless.txt` | Файл со ссылками для автозагрузки |
| `FILE_CHECK_INTERVAL` | `30` | Интервал проверки файла, сек |

## Как добавить прокси

**Через Telegram-бота** — отправьте ссылки `vless://` текстом или `.txt` файлом.

**Через файл** — создайте `vless.txt` со ссылками (по одной на строку, `#` — комментарий). Сервис загрузит файл при старте и удалит его. Если положить файл во время работы — подхватит через `FILE_CHECK_INTERVAL` секунд.

**Через REST API:**
```bash
curl -X POST http://127.0.0.1:8888/update \
  -H "Authorization: Bearer YOUR_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{"links": ["vless://..."]}'
```

## REST API

| Метод | Путь | Авторизация | Описание |
|---|---|---|---|
| GET | `/health` | — | Проверка живости сервиса |
| GET | `/status` | — | Статистика пула и список активных прокси |
| GET | `/proxy/list` | — | Список всех активных прокси |
| GET | `/proxy/random` | — | Случайный активный прокси |
| GET | `/proxy/best` | — | Прокси с минимальной задержкой |
| POST | `/update` | Bearer | Загрузить новые VLESS ссылки |

Пример использования прокси из ответа API:
```python
import httpx

info = httpx.get("http://127.0.0.1:8888/proxy/best").json()
# info["proxy_url"] == "socks5://127.0.0.1:10800"

with httpx.Client(proxy=info["proxy_url"]) as client:
    print(client.get("https://example.com").status_code)
```

## Подробная документация

- [Архитектура и обзор](project_docs/ru/00-overview.md)
- [Конфигурация](project_docs/ru/01-config.md)
- [Парсер VLESS ссылок](project_docs/ru/02-parser.md)
- [Хранилище (SQLite)](project_docs/ru/03-storage.md)
- [Управление xray-core](project_docs/ru/04-xray.md)
- [Проверка живости](project_docs/ru/05-health.md)
- [Оркестратор](project_docs/ru/06-manager.md)
- [REST API](project_docs/ru/07-api.md)
- [Telegram-бот](project_docs/ru/08-bot.md)
- [Файловый вотчер](project_docs/ru/09-watcher.md)
- [Деплой (systemd)](project_docs/ru/10-systemd.md)

---

[English version](README.md)
