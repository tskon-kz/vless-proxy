# REST API (`api/server.py`)

## Создание приложения

```python
from api.server import create_api
app = create_api(manager)  # FastAPI instance
```

Swagger UI и ReDoc отключены (`docs_url=None, redoc_url=None`).

## Эндпоинты

### `GET /health`

Проверка живости сервиса. Всегда возвращает 200.

```json
{ "status": "ok" }
```

---

### `GET /proxy/list`

Список всех активных прокси с запущенными xray-процессами.

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

Случайный активный прокси. Возвращает тот же формат что `/proxy/list[0]`.

503 если нет активных прокси:
```json
{ "error": "no_active_proxies", "message": "No active proxies available" }
```

---

### `GET /proxy/best`

Прокси с минимальной задержкой (`latency_ms`). Прокси без измеренной задержки не участвуют в выборке.

503 если нет кандидатов.

---

### `GET /status`

Подробный статус пула.

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

Загрузить новые VLESS ссылки. Требует Bearer-токен.

Если `API_SECRET_KEY` не задан — возвращает 404 (эндпоинт скрыт).

**Запрос:**
```bash
curl -X POST http://127.0.0.1:8888/update \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"links": ["vless://..."]}'
```

**Ответ:**
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

401 при неверном токене, 422 при неверном теле запроса.

## Авторизация

```python
def _bearer_auth(request: Request) -> None:
    if not settings.API_SECRET_KEY:
        raise HTTPException(status_code=404)
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != settings.API_SECRET_KEY:
        raise HTTPException(status_code=401)
```

Возврат 404 (а не 401) при отсутствии ключа намеренный — не раскрывает факт существования эндпоинта.
