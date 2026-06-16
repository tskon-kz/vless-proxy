# Telegram Bot (`bot/bot.py`, `bot/strings.py`)

[Русский](../ru/08-bot.md)

## Creating the bot

```python
from bot.bot import create_bot
bot, dp = create_bot(manager)
await dp.start_polling(bot, allowed_updates=["message"])
```

`create_bot` returns `(Bot, Dispatcher)`. The `manager` is injected into handlers via `dp["manager"] = manager`.

When `TG_BOT_PROXY` is set, `Bot` is created with `AiohttpSession(proxy=...)` — all Telegram API requests go through the specified proxy (SOCKS5/HTTP). Needed when the server cannot reach Telegram directly.

## Access control

All messages pass through `AccessMiddleware`. The bot silently ignores messages from users not in `TG_ALLOWED_USER_IDS` — no errors, no replies.

## Commands

| Command | What it does |
|---------|-------------|
| `/start` | Welcome message and command list |
| `/help` | Explanation of the link format |
| `/status` | Pool state: counters + active proxy list with ports and latency |
| `/check` | Trigger an immediate check of all proxies (`manager.force_recheck()`) |

## Adding proxies

**As text** — if a message contains `vless://`, all links are extracted and passed to `manager.update_proxies(source="telegram")`.

**As a file** — `.txt` files and files without extension (`mime_type=None`) are accepted. Content is processed as plain text. Other formats are rejected with an error message.

Both methods reply with a report: total received, valid, invalid. A liveness check is then started in the background.

## Status change notifications

When `TG_NOTIFY_CHAT_ID` is set, `create_bot` installs `manager.notify_callback`. On every proxy status change a message is sent to that chat:

- Proxy came alive: name, host, latency
- Proxy died: name, host, consecutive failure count

## Strings (`bot/strings.py`)

All user-facing text is in `bot/strings.py`. The manager and other modules contain no Russian text — only `strings.py` and `parser.py` (error summaries).

Public interface:

```python
START: str                    # welcome message
HELP: str                     # link format reference
CHECK_STARTED: str            # "starting check..."
FILE_UNSUPPORTED: str         # error for wrong file format

processing(count) → str
update_result(total, valid, invalid, errors) → str
status_message(active, dead, pending, invalid, proxies) → str
proxy_alive(name, host, port, latency_ms) → str    # notification
proxy_dead(name, host, port, fail_count) → str     # notification
```
