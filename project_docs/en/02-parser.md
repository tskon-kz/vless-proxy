# VLESS Link Parser (`core/parser.py`)

[Русский](../ru/02-parser.md)

## VLESS URI format

```
vless://<uuid>@<host>:<port>?<params>#<name>
```

Example:
```
vless://9d507afd-7e90-4b7e-8bd8-6877f7a304ae@1.2.3.4:443?security=reality&sni=example.com&pbk=KEY&sid=AB12#Amsterdam
```

## Data structures

### `VlessConfig`

Dataclass holding all fields of a parsed link:

| Field | Description |
|-------|-------------|
| `uuid` | User UUID |
| `host` | Server address |
| `port` | Server port |
| `raw_uri` | Original string (used as unique key in DB) |
| `name` | Name from URI fragment (`#Name`) |
| `type` | Transport: `tcp`, `ws`, `grpc`, etc. |
| `security` | Security: `none`, `tls`, `reality` |
| `flow` | XTLS flow: `xtls-rprx-vision` or empty |
| `sni` | Server Name Indication |
| `fp` | Browser fingerprint |
| `alpn` | Comma-separated: `h2,http/1.1` |
| `pbk` | Reality public key |
| `sid` | Reality Short ID |
| `path` | WebSocket path |
| `host_header` | WebSocket Host header |
| `service_name` | gRPC service name |

### `ParseResult`

```python
@dataclass
class ParseResult:
    success: bool
    raw_uri: str
    config: VlessConfig | None   # set when success=True
    error: str                   # set when success=False
```

## Public functions

### `parse_vless(uri) → ParseResult`

Parses a single link. Returns `ParseResult` with `success=False` and an error description if the link is invalid.

```python
result = parse_vless("vless://...")
if result.success:
    print(result.config.host)
```

### `validate_config(config) → list[str]`

Validates a parsed config. Returns a list of error messages (empty = valid):

- UUID must be a valid UUID4
- Host must not be empty; a hostname without a dot (except `localhost`) is rejected
- Port must be in range 1–65535
- Transport type must be one of: `tcp`, `ws`, `grpc`, `http`, `kcp`, `quic`
- WebSocket: `path` must start with `/`
- Reality: `pbk` and `sni` are required
- `flow=xtls-rprx-vision` requires `security=reality` or `security=tls`

### `parse_vless_list(text) → (list[VlessConfig], list[ParseResult])`

Parses text containing multiple links. Links can be separated by spaces or newlines, embedded in arbitrary text — the function extracts everything starting with `vless://`.

Deduplication by `(uuid, host, port)` — if the same server appears multiple times (e.g. with different `#name`), only the first is kept.

```python
configs, results = parse_vless_list(text)
# configs — successfully parsed, deduplicated
# results — all attempts including errors (for reporting)
```

### `generate_summary(results) → str`

Builds a human-readable report: counts of valid/invalid links and a list of errors.
