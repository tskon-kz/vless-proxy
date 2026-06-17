# Парсер VLESS-ссылок (`core/parser.py`)

[English](../en/02-parser.md)

## `parse_vless(uri: str) -> ParseResult`

Парсит одну `vless://` ссылку. Возвращает `ParseResult` с полями:
- `success: bool`
- `config: VlessConfig | None` — заполняется при успехе
- `raw_uri: str` — канонический URI (фрагмент убран, query-параметры отсортированы по алфавиту)
- `error: str` — описание ошибки при неудаче

`raw_uri` — ключ идентификации в базе данных. Сортировка параметров гарантирует, что один и тот же сервер, возвращённый подпиской с разным порядком параметров, не создаст дублирующую запись в БД.

## `parse_vless_list(text: str) -> tuple[list[VlessConfig], list[ParseResult]]`

Парсит список URI, разделённых переносами строк. Пропускает пустые строки и строки без `vless://`. Дедублицирует по `raw_uri`.

## Поля `VlessConfig`

| Поле | Описание |
|---|---|
| `uuid` | UUID пользователя VLESS |
| `host` | Хост или IP сервера |
| `port` | Порт сервера |
| `raw_uri` | Канонический URI без фрагмента |
| `name` | Отображаемое имя (декодируется из `#fragment`) |
| `type` | Транспорт: `tcp`, `ws`, `grpc`, `http`, `kcp`, `quic` |
| `security` | Безопасность: `none`, `tls`, `reality` |
| `flow` | Flow control (например `xtls-rprx-vision`) |
| `sni` | SNI для TLS/Reality |
| `fp` | TLS fingerprint |
| `pbk` | Публичный ключ Reality |
| `sid` | Short ID для Reality |
| `path` | Путь WebSocket |
| `service_name` | Имя gRPC-сервиса |

## Валидация

`validate_config()` проверяет:
- Формат UUID
- Корректность хоста (IP или hostname с точкой)
- Диапазон порта (1–65535)
- Известный тип транспорта
- Путь WebSocket начинается с `/`
- Reality требует `pbk` и `sni`
- Flow `xtls-rprx-vision` требует `security=reality` или `security=tls`
