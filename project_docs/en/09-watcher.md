# File Watcher (`core/watcher.py`)

[Русский](../ru/09-watcher.md)

## Purpose

Allows updating the proxy list without using the Telegram bot or API — just drop a `vless.txt` file into the project directory.

## Behaviour

**File handling logic:**

1. File does not exist → do nothing, keep waiting
2. File is empty (0 bytes or only whitespace) → do nothing, wait for content to appear
3. File contains only comments (`#...`) or non-VLESS lines → do nothing
4. File contains at least one `vless://` link → load, **delete the file**

The file is deleted after a successful load. This is the key design decision: on the next restart the file is gone and the DB state is not overwritten.

If loading fails with an error — the file is **not deleted**, so it can be corrected and retried.

## File format

```
# Lines starting with # are comments and are ignored
vless://uuid1@host1:443?security=reality&...#Name1
vless://uuid2@host2:443?security=tls&...#Name2

# Temporarily disabled server:
# vless://uuid3@host3:443?...#Name3
```

## Usage

```python
watcher = FileWatcher(manager)
await watcher.load_once()                          # load file on startup (if present)
asyncio.create_task(watcher.run_forever())         # background polling
```

### `load_once() → bool`

Called once at service startup. If the file exists and contains links — loads and deletes it. Returns `True` if a load was performed.

### `run_forever()`

Infinite loop: every `FILE_CHECK_INTERVAL` seconds calls `_check_file()`.

### `_check_file()`

Internal polling method:
- Computes the SHA-256 hash of the file
- If the file is empty — returns without updating the hash (will check again next tick)
- If the hash matches the previous one — skips
- If the hash is new — reads and loads

The hash is updated **only after successfully reading a non-empty file**. An empty file does not set the hash — this allows creating the file first (`touch vless.txt`) and filling it later; the watcher will not miss when content appears.

## Settings

| Variable | Default | Description |
|---|---|---|
| `VLESS_FILE` | `./vless.txt` | File path |
| `FILE_CHECK_INTERVAL` | `30` | Polling interval, seconds |

## Update workflow

```bash
# 1. Create the file (can be done in advance — watcher waits for content)
touch vless.txt

# 2. Fill it with links
echo "vless://..." >> vless.txt
echo "vless://..." >> vless.txt

# 3. Or via the helper script
echo "vless://..." | bash scripts/update-proxies.sh

# Within FILE_CHECK_INTERVAL seconds the file will be read and deleted
```
