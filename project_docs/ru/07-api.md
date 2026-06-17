# REST API (`api/server.py`)

[English](../en/07-api.md)

API поднимается на FastAPI + uvicorn. Swagger UI отключён.

## Эндпоинты

### `GET /proxy/best`

Возвращает самый быстрый активный прокси. После каждого цикла проверок самый быстрый прокси переносится на `PROXY_PORT_START`, поэтому дополнительного измерения задержки здесь не требуется.

**Ответ 200:**
```json
{"url": "socks5://127.0.0.1:10800"}
```

**Ответ 503** (нет активных прокси):
```json
{"error": "no active proxies"}
```

---

### `GET /proxy/list`

Возвращает все активные прокси в виде JSON-массива, отсортированного по порту.

**Ответ 200:**
```json
["socks5://127.0.0.1:10800", "socks5://127.0.0.1:10801"]
```

Возвращает `[]`, если активных прокси нет.

## Примеры использования

```bash
# Shell: получить лучший прокси
PROXY=$(curl -sf http://127.0.0.1:8888/proxy/best | jq -r .url)
curl --proxy "$PROXY" https://example.com

# Python
import httpx
url = httpx.get("http://127.0.0.1:8888/proxy/best").json()["url"]
with httpx.Client(proxy=url) as client:
    print(client.get("https://example.com").status_code)
```

## Доступ снаружи

По умолчанию API слушает только `127.0.0.1`. Чтобы открыть доступ с других хостов:

```env
API_HOST=0.0.0.0
PROXY_BIND_HOST=1.2.3.4   # реальный IP сервера; встраивается в URL прокси в ответах API
```
