# Модуль 7: REST API

## Задача

Реализовать `api/server.py` — лёгкий HTTP сервер для клиентских сервисов (axios, aiogram и др.). Слушает только на localhost. Клиентский код делает запрос и получает готовые параметры прокси.

## Что реализовать

### Эндпоинты

**`GET /proxy/list`**

Все живые прокси с запущенными процессами.

Ответ:
```json
{
  "count": 5,
  "proxies": [
    {
      "protocol": "socks5",
      "host": "127.0.0.1",
      "port": 10801,
      "proxy_url": "socks5://127.0.0.1:10801",
      "name": "Amsterdam, Netherlands",
      "latency_ms": 142,
      "last_check": 1703123456.789
    }
  ]
}
```

**`GET /proxy/random`**

Один случайный живой прокси. Если живых нет — 503.

Ответ при успехе (200):
```json
{
  "protocol": "socks5",
  "host": "127.0.0.1",
  "port": 10803,
  "proxy_url": "socks5://127.0.0.1:10803",
  "name": "Frankfurt, Germany",
  "latency_ms": 98
}
```

Ответ при отсутствии живых прокси (503):
```json
{
  "error": "no_active_proxies",
  "message": "No active proxies available"
}
```

**`GET /proxy/best`**

Прокси с наименьшей latency среди живых. Если нет живых — 503.

Ответ — тот же формат что и `/proxy/random`.

**`GET /status`**

Полный статус пула для мониторинга.

Ответ:
```json
{
  "pool": {
    "active": 5,
    "dead": 2,
    "pending": 0,
    "invalid": 1,
    "running_processes": 5
  },
  "check_url": "https://www.linkedin.com",
  "check_interval_seconds": 300,
  "uptime_seconds": 3600,
  "proxies": [
    {
      "name": "Amsterdam",
      "host": "155.117.137.168",
      "status": "active",
      "local_port": 10801,
      "latency_ms": 142,
      "last_check": 1703123456.789,
      "fail_count": 0
    }
  ]
}
```

**`POST /update`**

Альтернативный способ обновления ссылок (помимо бота и файла). Для скриптов и автоматизации. Требует Bearer токен (`API_SECRET_KEY` в конфиге).

Запрос:
```json
{
  "links": [
    "vless://uuid@host:port?...#name",
    "vless://uuid2@host2:port2?...#name2"
  ]
}
```

Ответ (200):
```json
{
  "total_received": 5,
  "valid": 4,
  "invalid": 1,
  "newly_added": 3,
  "removed": 1,
  "errors": [
    "vless://bad-uuid@... — невалидный UUID"
  ]
}
```

Авторизация:
```
Authorization: Bearer <API_SECRET_KEY>
```
Если ключ не совпадает — 401. Если `API_SECRET_KEY` не задан в конфиге — эндпоинт отключён, возвращает 404.

**`GET /health`**

Простая проверка что сервис запущен. Для healthcheck в systemd или docker.

Ответ (200):
```json
{ "status": "ok" }
```

### Реализация

Использовать FastAPI. Приложение создаётся через factory функцию:

```python
def create_api(manager: ProxyManager) -> FastAPI:
    app = FastAPI(title="VLESS Proxy Manager", docs_url=None, redoc_url=None)
    # ... регистрировать роутеры
    return app
```

`docs_url=None` — отключить Swagger UI (лишнее для локального сервиса).

Запускать через uvicorn:
```python
config = uvicorn.Config(
    app,
    host=settings.API_HOST,
    port=settings.API_PORT,
    log_level="warning"   # не засорять логи каждым запросом
)
server = uvicorn.Server(config)
await server.serve()
```

### Добавить в `config.py`

```
API_SECRET_KEY   — ключ для /update эндпоинта, дефолт: "" (эндпоинт отключён)
```

## Примеры использования клиентами

### Python + aiohttp

```python
async def get_proxy() -> str:
    async with aiohttp.ClientSession() as s:
        async with s.get("http://127.0.0.1:8888/proxy/random") as r:
            if r.status == 503:
                raise RuntimeError("No proxies available")
            data = await r.json()
            return data["proxy_url"]  # "socks5://127.0.0.1:10803"

# Использование:
proxy_url = await get_proxy()
async with aiohttp.ClientSession() as session:
    async with session.get("https://example.com", proxy=proxy_url) as resp:
        ...
```

### aiogram 3.x

```python
import aiohttp
from aiogram import Bot

async def create_bot_with_proxy(token: str) -> Bot:
    async with aiohttp.ClientSession() as s:
        async with s.get("http://127.0.0.1:8888/proxy/random") as r:
            data = await r.json()
    proxy_url = data["proxy_url"]
    return Bot(token=token, proxy=proxy_url)
```

### Node.js + axios

```javascript
const response = await axios.get('http://127.0.0.1:8888/proxy/random')
const { host, port } = response.data

const result = await axios.get('https://api.example.com', {
  proxy: { host, port, protocol: 'socks5' }
})
```

### curl

```bash
PORT=$(curl -s http://127.0.0.1:8888/proxy/random | python3 -c "import sys,json; print(json.load(sys.stdin)['port'])")
curl --socks5 127.0.0.1:$PORT https://www.linkedin.com
```

Добавить эти примеры в `README.md`.

## Что НЕ нужно

- Аутентификация на read-only эндпоинтах (`/proxy/*`, `/status`, `/health`)
- Rate limiting
- HTTPS — только HTTP, только localhost
- Пагинация — прокси не может быть настолько много
