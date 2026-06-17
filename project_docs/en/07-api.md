# REST API (`api/server.py`)

[Русский](../ru/07-api.md)

The API is served by FastAPI + uvicorn. Swagger UI is disabled.

## Endpoints

### `GET /proxy/best`

Returns the fastest active proxy. The fastest proxy is always reordered to `PROXY_PORT_START` after each health cycle, so no additional latency measurement is needed here.

**Response 200:**
```json
{"url": "socks5://127.0.0.1:10800"}
```

**Response 503** (no active proxies):
```json
{"error": "no active proxies"}
```

---

### `GET /proxy/list`

Returns all active proxy URLs as a plain JSON array, sorted by port.

**Response 200:**
```json
["socks5://127.0.0.1:10800", "socks5://127.0.0.1:10801"]
```

Returns `[]` if no proxies are active.

## Usage examples

```bash
# Shell: get best proxy
PROXY=$(curl -sf http://127.0.0.1:8888/proxy/best | jq -r .url)
curl --proxy "$PROXY" https://example.com

# Python
import httpx
url = httpx.get("http://127.0.0.1:8888/proxy/best").json()["url"]
with httpx.Client(proxy=url) as client:
    print(client.get("https://example.com").status_code)
```

## External access

By default the API listens on `127.0.0.1`. To expose it to other hosts:

```env
API_HOST=0.0.0.0
PROXY_BIND_HOST=1.2.3.4   # real server IP; embedded in proxy URLs returned by the API
```
