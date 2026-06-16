# Парсер VLESS-ссылок (`core/parser.py`)

[English](../en/02-parser.md)

## Формат VLESS URI

```
vless://<uuid>@<host>:<port>?<params>#<name>
```

Пример:
```
vless://9d507afd-7e90-4b7e-8bd8-6877f7a304ae@1.2.3.4:443?security=reality&sni=example.com&pbk=KEY&sid=AB12#Amsterdam
```

## Структуры данных

### `VlessConfig`

Датакласс, хранящий все поля разобранной ссылки:

| Поле | Описание |
|------|----------|
| `uuid` | UUID пользователя |
| `host` | Адрес сервера |
| `port` | Порт сервера |
| `raw_uri` | Исходная строка (используется как уникальный ключ в БД) |
| `name` | Имя из фрагмента URI (`#Название`) |
| `type` | Транспорт: `tcp`, `ws`, `grpc` и др. |
| `security` | Безопасность: `none`, `tls`, `reality` |
| `flow` | Поток XTLS: `xtls-rprx-vision` или пусто |
| `sni` | Server Name Indication |
| `fp` | Fingerprint браузера |
| `alpn` | Через запятую: `h2,http/1.1` |
| `pbk` | Публичный ключ Reality |
| `sid` | Short ID для Reality |
| `path` | Путь для WebSocket |
| `host_header` | Host-заголовок для WebSocket |
| `service_name` | Имя сервиса для gRPC |

### `ParseResult`

```python
@dataclass
class ParseResult:
    success: bool
    raw_uri: str
    config: VlessConfig | None   # заполнен при success=True
    error: str                   # заполнен при success=False
```

## Публичные функции

### `parse_vless(uri) → ParseResult`

Парсит одну ссылку. Возвращает `ParseResult` с `success=False` и описанием ошибки если ссылка невалидна.

```python
result = parse_vless("vless://...")
if result.success:
    print(result.config.host)
```

### `validate_config(config) → list[str]`

Проверяет распарсенный конфиг на корректность. Возвращает список ошибок (пустой = всё хорошо):

- UUID должен быть валидным UUID4
- Host не может быть пустым; hostname без точки (кроме `localhost`) отклоняется
- Port в диапазоне 1–65535
- Transport type должен быть из: `tcp`, `ws`, `grpc`, `http`, `kcp`, `quic`
- WebSocket: `path` должен начинаться с `/`
- Reality: обязательны `pbk` и `sni`
- `flow=xtls-rprx-vision` требует `security=reality` или `security=tls`

### `parse_vless_list(text) → (list[VlessConfig], list[ParseResult])`

Парсит текст, содержащий несколько ссылок. Ссылки могут быть разделены пробелами, переносами строк, находиться в произвольном тексте — функция извлекает всё начинающееся с `vless://`.

Дедупликация по ключу `(uuid, host, port)` — если одна ссылка повторяется с разными параметрами (например, разным `#name`), берётся первая.

```python
configs, results = parse_vless_list(text)
# configs — только успешно разобранные, без дублей
# results — все попытки, включая ошибки (для отчёта)
```

### `generate_summary(results) → str`

Формирует читаемый текст-отчёт: сколько валидных, сколько с ошибками, и перечень ошибок.
