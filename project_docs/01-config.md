# Модуль 1: конфиг и структура проекта

## Задача

Создать `config.py` — единственное место для всех настроек. Все остальные модули импортируют настройки оттуда. Никаких хардкодов в коде модулей.

## Что реализовать

### `config.py`

Датакласс или Pydantic Settings с полями ниже. Значения читаются из переменных окружения, если переменная не задана — используется дефолт.

```
Telegram:
  TG_BOT_TOKEN        — токен бота (обязательное, без дефолта)
  TG_ALLOWED_USER_IDS — список int через запятую, кто может управлять ботом

xray:
  XRAY_BINARY         — путь к бинарнику xray, дефолт: /usr/local/bin/xray
  XRAY_CONFIG_DIR     — директория для временных конфигов, дефолт: /tmp/vless-manager

Пул прокси:
  PROXY_PORT_START    — первый порт пула, дефолт: 10800
  PROXY_PORT_END      — последний порт пула, дефолт: 10820
  PROXY_BIND_HOST     — на каком адресе слушать SOCKS5, дефолт: 127.0.0.1

Health check:
  CHECK_URL           — URL для проверки живости, дефолт: https://www.linkedin.com
  CHECK_TIMEOUT       — таймаут одной проверки в секундах, дефолт: 10
  CHECK_INTERVAL      — интервал фоновых проверок в секундах, дефолт: 300
  CHECK_STARTUP_XRAY_WAIT — сколько секунд ждать после запуска xray перед проверкой, дефолт: 2

REST API:
  API_HOST            — дефолт: 127.0.0.1
  API_PORT            — дефолт: 8888

Storage:
  DB_PATH             — путь к SQLite файлу, дефолт: ./state.db

File watcher:
  VLESS_FILE          — путь к fallback файлу со ссылками, дефолт: ./vless.txt
  FILE_CHECK_INTERVAL — как часто проверять файл на изменения в секундах, дефолт: 30
```

### `.env.example`

Создать файл с примерами всех переменных и комментариями на английском.

### `requirements.txt`

```
aiogram==3.13.1
fastapi==0.115.5
uvicorn==0.32.1
aiosqlite==0.20.0
aiohttp==3.11.9
aiofiles==24.1.0
python-dotenv==1.0.1
pydantic-settings==2.6.1
watchdog==6.0.0
```

Брать свежие версии библиотек, но чтобы не конфликтовал функционал, а выше просто пример.

### `install-xray.sh`

Bash-скрипт для установки xray-core на Ubuntu. Должен:
- определить архитектуру (`uname -m`): если x86_64 → скачать `Xray-linux-64.zip`, если aarch64 → `Xray-linux-arm64-v8a.zip`
- скачать последний релиз с `https://github.com/XTLS/Xray-core/releases/latest/download/`
- распаковать, положить бинарник в `/usr/local/bin/xray`
- `chmod +x /usr/local/bin/xray`
- проверить: `xray version`

### Скелеты пакетов

Создать пустые `__init__.py` во всех директориях: `core/`, `api/`, `bot/`, `watcher/`.

## Как читать конфиг

Использовать `pydantic-settings` с `BaseSettings`. Файл `.env` подгружается автоматически если есть. Переменные окружения имеют приоритет над `.env`.

Пример использования в других модулях:
```python
from config import settings
xray_path = settings.XRAY_BINARY
```

## Проверки при старте

В `config.py` добавить метод `validate()` который проверяет:
- `TG_BOT_TOKEN` задан
- `XRAY_BINARY` существует на диске (если нет — warning, не exception, сервис может стартовать без xray для дебага)
- `PROXY_PORT_START < PROXY_PORT_END`
- `PROXY_PORT_END - PROXY_PORT_START >= 1` (минимум 2 порта в пуле)

## Что НЕ нужно

- Никаких YAML/TOML конфигов — только `.env` + переменные окружения
- Не делать конфиг синглтоном через хитрые паттерны — просто `settings = Settings()` на уровне модуля
