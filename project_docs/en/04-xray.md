# xray-core Management (`core/xray.py`)

[Русский](../ru/04-xray.md)

## `XrayProcessPool`

Manages a set of persistent xray subprocess instances, one per active proxy.

### Key methods

| Method | Description |
|---|---|
| `start_proxy(proxy_id, config, port?)` | Write xray config, start process, record in DB |
| `stop_proxy(proxy_id)` | Terminate xray process, clean up DB entry |
| `stop_all()` | Stop all running processes (called on shutdown) |
| `get_process(proxy_id)` | Return `ProcessRow` for a proxy, or `None` |
| `get_all_ports()` | Return `{proxy_id: local_port}` for all running processes |

### Port allocation

If no port is specified in `start_proxy()`, the pool calls `storage.get_available_port()` to find the lowest free port in `PROXY_PORT_START..PROXY_PORT_END`. Returns `None` if all ports are taken.

## `write_xray_config(config, port, config_path)`

Generates a JSON xray config file for a VLESS outbound + SOCKS5 inbound. Handles all transport types (TCP, WebSocket, gRPC) and security layers (none, TLS, Reality).

## Health check process

`check_proxy()` in `core/health.py` uses a separate temporary xray process (on a port from the `19900+` range) for each health check — this range never overlaps with the SOCKS5 pool. The temporary process is started, the HTTP check is performed, then the process is terminated regardless of the result.
