# xray-core Management (`core/xray.py`)

[Русский](../ru/04-xray.md)

## Overview

The module does two things:
1. Generates xray-core JSON configs from VLESS parameters
2. Manages child xray processes (`XrayProcess`, `XrayProcessPool`)

## Config generation

### `generate_xray_config(config, local_port) → dict`

Builds an xray config dict. Structure:

```json
{
  "log": { "loglevel": "warning" },
  "inbounds": [{
    "listen": "127.0.0.1",
    "port": 10800,
    "protocol": "socks",
    "settings": { "udp": true }
  }],
  "outbounds": [{
    "protocol": "vless",
    "settings": { "vnext": [{ "address": "...", "port": 443, "users": [...] }] },
    "streamSettings": { ... }
  }]
}
```

`flow` is only added to `users` when non-empty — xray rejects an empty string.

### `write_xray_config(config, local_port, config_dir) → str`

Writes the config to `<config_dir>/proxy_<local_port>.json`. Creates the directory if it does not exist. Returns the file path.

### Supported transports

| transport | security | Generated settings |
|-----------|----------|--------------------|
| `tcp` | `reality` | `realitySettings` |
| `tcp` | `tls` | `tlsSettings` |
| `tcp` | `none` | `tcpSettings` with `headerType` |
| `ws` | any | `wsSettings` + optional tls/reality |
| `grpc` | any | `grpcSettings` + optional tls/reality |

## Process management

### `XrayProcess`

Wrapper around a single xray child process.

```python
proc = XrayProcess(proxy_id, local_port, config_path, storage)
pid = await proc.start()    # launch, returns PID
await proc.stop()           # SIGTERM → 5 s wait → SIGKILL; deletes config file
alive = await proc.is_alive()
```

On start a background `_monitor()` task is created that waits for the process to exit and updates the DB status to `crashed` on unexpected exit.

### `XrayProcessPool`

Keeps all running processes in a `{proxy_id: XrayProcess}` dict.

```python
pool = XrayProcessPool(storage)

proc = await pool.start_proxy(proxy_id, config)
# 1. Gets a free port from the DB
# 2. Writes the xray config to disk
# 3. Creates XrayProcess and starts it
# 4. Saves PID to the DB

await pool.stop_proxy(proxy_id)
await pool.restart_proxy(proxy_id, new_config)
await pool.stop_all()

ports = pool.get_all_ports()  # {proxy_id: local_port}
```

If no ports are available, `start_proxy` returns `None` and logs a warning.
