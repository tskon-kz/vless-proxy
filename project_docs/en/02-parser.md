# VLESS Parser (`core/parser.py`)

[Русский](../ru/02-parser.md)

## `parse_vless(uri: str) -> ParseResult`

Parses a single `vless://` URI. Returns a `ParseResult` with:
- `success: bool`
- `config: VlessConfig | None` — populated on success
- `raw_uri: str` — canonical URI (fragment stripped, query params sorted alphabetically)
- `error: str` — error message on failure

The canonical `raw_uri` is the identity key used in the database. Sorting query params ensures that the same server returned with different parameter order across subscription fetches produces the same key and does not create duplicate DB entries.

## `parse_vless_list(text: str) -> tuple[list[VlessConfig], list[ParseResult]]`

Parses a newline-separated list of URIs. Skips blank lines and non-`vless://` lines. Deduplicates by `raw_uri`.

## `VlessConfig` fields

| Field | Description |
|---|---|
| `uuid` | VLESS user UUID |
| `host` | Server hostname or IP |
| `port` | Server port |
| `raw_uri` | Canonical URI without fragment |
| `name` | Display name (decoded from `#fragment`) |
| `type` | Transport type: `tcp`, `ws`, `grpc`, `http`, `kcp`, `quic` |
| `security` | Security layer: `none`, `tls`, `reality` |
| `flow` | Flow control (e.g. `xtls-rprx-vision`) |
| `sni` | TLS/Reality SNI |
| `fp` | TLS fingerprint |
| `pbk` | Reality public key |
| `sid` | Reality short ID |
| `path` | WebSocket path |
| `service_name` | gRPC service name |

## Validation

`validate_config()` checks:
- UUID format
- Host validity (IP or hostname with a dot)
- Port range (1–65535)
- Known transport type
- WebSocket path starts with `/`
- Reality requires `pbk` and `sni`
- `xtls-rprx-vision` flow requires `reality` or `tls` security
