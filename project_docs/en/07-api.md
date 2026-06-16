# REST API (`api/server.py`)

[Русский](../ru/07-api.md)

## Creating the app

```python
from api.server import create_api
app = create_api(manager)  # FastAPI instance
```

Swagger UI and ReDoc are disabled (`docs_url=None, redoc_url=None`).

## Endpoints

### `GET /health`

Service liveness check. Always returns 200.

```json
{ "status": "ok" }
```

---

### `GET /proxy/list`

All active proxies with running xray processes.

```json
{
  "count": 2,
  "proxies": [
    {
      "protocol": "socks5",
      "host": "127.0.0.1",
      "port": 10800,
      "proxy_url": "socks5://127.0.0.1:10800",
      "name": "Amsterdam",
      "latency_ms": 142,
      "last_check": 1718000000.0
    }
  ]
}
```

---

### `GET /proxy/random`

A random active proxy. Same response shape as a single item from `/proxy/list`.

503 when no active proxies:
```json
{ "error": "no_active_proxies", "message": "No active proxies available" }
```

---

### `GET /proxy/best`

The proxy with the lowest `latency_ms`. Proxies without a measured latency are excluded.

503 when no candidates.

---

### `GET /status`

Detailed pool status.

```json
{
  "pool": {
    "active": 3, "dead": 1, "pending": 0,
    "invalid": 0, "running_processes": 3
  },
  "check_url": "https://www.linkedin.com",
  "check_interval_seconds": 300,
  "uptime_seconds": 3600.5,
  "proxies": [
    {
      "name": "Amsterdam",
      "host": "1.2.3.4",
      "status": "active",
      "local_port": 10800,
      "latency_ms": 142,
      "last_check": 1718000000.0,
      "fail_count": 0
    }
  ]
}
```

---

### `POST /update`

Submit new VLESS links. Requires a Bearer token.

If `API_SECRET_KEY` is not set — returns 404 (endpoint is hidden).

**Request:**
```bash
curl -X POST http://127.0.0.1:8888/update \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"links": ["vless://..."]}'
```

**Response:**
```json
{
  "total_received": 5,
  "valid": 4,
  "invalid": 1,
  "newly_added": 2,
  "removed": 1,
  "errors": ["URI must start with vless://: ..."]
}
```

401 on wrong token, 422 on malformed request body.

## Authentication

```python
def _bearer_auth(request: Request) -> None:
    if not settings.API_SECRET_KEY:
        raise HTTPException(status_code=404)
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != settings.API_SECRET_KEY:
        raise HTTPException(status_code=401)
```

Returning 404 (not 401) when no key is configured is intentional — it does not reveal the existence of the endpoint.
