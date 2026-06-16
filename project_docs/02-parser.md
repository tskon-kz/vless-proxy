# Модуль 2: парсер и валидатор VLESS URI

## Задача

Реализовать `core/parser.py` — парсинг VLESS URI в структурированный объект и валидацию с детальными ошибками.

## Формат VLESS URI

```
vless://<uuid>@<host>:<port>?<query_params>#<name>
```

Пример:
```
vless://9d507afd-7e90-4b7e-8bd8-6877f7a304ae@155.117.137.168:443?flow=xtls-rprx-vision&type=tcp&headerType=none&security=reality&fp=firefox&sni=cdn3-87.yahoo.com&pbk=CMkW1axrhEX...&sid=7e77e7e2cf2b7a79#Amsterdam
```

## Что реализовать

### Датакласс `VlessConfig`

```python
@dataclass
class VlessConfig:
    # Обязательные поля
    uuid: str
    host: str
    port: int
    raw_uri: str          # оригинальная строка как есть
    name: str             # из fragment (#...), URL-decoded, дефолт: ""

    # Параметры транспорта
    type: str             # tcp | ws | grpc | http | kcp, дефолт: tcp
    security: str         # none | tls | reality, дефолт: none
    flow: str             # xtls-rprx-vision | "", дефолт: ""
    header_type: str      # none | http, дефолт: none

    # TLS параметры
    sni: str              # дефолт: ""
    fp: str               # fingerprint, дефолт: ""
    alpn: str             # дефолт: ""

    # Reality параметры
    pbk: str              # public key, дефолт: ""
    sid: str              # short id, дефолт: ""
    spx: str              # spider x, дефолт: ""

    # WebSocket параметры
    path: str             # дефолт: "/"
    host_header: str      # заголовок Host для WS, дефолт: ""

    # gRPC параметры
    service_name: str     # дефолт: ""
```

### Датакласс `ParseResult`

```python
@dataclass
class ParseResult:
    success: bool
    config: VlessConfig | None    # None если success=False
    error: str                    # описание ошибки если success=False, "" если OK
    raw_uri: str                  # оригинальная строка
```

### Функция `parse_vless(uri: str) -> ParseResult`

Основная функция парсинга. Алгоритм:

1. Проверить что строка начинается с `vless://`
2. Распарсить через `urllib.parse.urlparse`
3. Извлечь UUID из `netloc` (часть до `@`)
4. Извлечь host и port
5. Распарсить query params через `urllib.parse.parse_qs`
6. Заполнить `VlessConfig`
7. Вызвать `validate_config(config)` — если есть ошибки, вернуть `ParseResult(success=False, error=...)`
8. Вернуть `ParseResult(success=True, config=config)`

### Функция `validate_config(config: VlessConfig) -> list[str]`

Возвращает список ошибок (пустой список = всё ок). Проверки:

**UUID:**
- Валидный UUID v4 формат через `uuid.UUID(config.uuid)`

**Host:**
- Не пустой
- Если IP — валидный IPv4 или IPv6 через `ipaddress` модуль
- Если hostname — содержит хотя бы одну точку или является `localhost`
- Нет пробелов и спецсимволов

**Port:**
- Целое число от 1 до 65535

**Security + параметры:**
- Если `security == "reality"`: обязательны `pbk` и `sni`
- Если `security == "tls"`: `sni` желателен (warning, не ошибка)
- Если `flow == "xtls-rprx-vision"`: `security` должен быть `reality` или `tls`

**Transport:**
- `type` — одно из: `tcp`, `ws`, `grpc`, `http`, `kcp`, `quic`
- Если `type == "ws"`: `path` должен начинаться с `/`

### Функция `parse_vless_list(text: str) -> tuple[list[VlessConfig], list[ParseResult]]`

Принимает многострочный текст (или текст с пробелами). Возвращает:
- список успешно распарсенных конфигов
- список всех ParseResult (включая ошибочные) для отчёта

Логика разбивки входного текста:
- split по `\n`
- дополнительно split по пробелу (на случай если ссылки через пробел)
- strip каждой строки
- пропустить пустые строки и строки не начинающиеся с `vless://`
- дедупликация по `(uuid, host, port)` — одинаковые серверы не добавлять дважды

### Функция `generate_summary(results: list[ParseResult]) -> str`

Генерирует читаемый текст-отчёт для отправки в Telegram:
```
Обработано ссылок: 10
✅ Валидных: 8
❌ Невалидных: 2

Ошибки:
• vless://bad-uuid@... — невалидный UUID
• vless://...@host:99999 — порт вне диапазона
```

## Что НЕ нужно

- Не парсить `vmess://`, `trojan://` и другие протоколы — только `vless://`
- Не делать сетевых запросов — только синтаксическая валидация
- Не бросать исключений наружу — все ошибки в `ParseResult.error`

## Тесты

Создать `tests/test_parser.py` с pytest. Обязательные кейсы:
- валидная ссылка с reality (из примера выше)
- ссылка без `vless://` префикса
- невалидный UUID
- порт 0 и порт 99999
- отсутствие `pbk` при `security=reality`
- пустая строка
- `parse_vless_list` с миксом валидных и невалидных
- дедупликация одинаковых ссылок
