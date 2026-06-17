# Telegram Bot (`bot/bot.py`, `bot/strings.py`)

[Русский](../ru/08-bot.md)

Built with aiogram 3. Only users listed in `TG_ALLOWED_USER_IDS` can interact with the bot.

## Commands

| Command | Description |
|---|---|
| `/status` | Pool stats (active / dead / pending counts) and the list of running proxies with ports and latency |
| `/check` | Force-recheck all active and pending servers immediately |
| `/help` | Help message with available commands |

The bot command menu is registered with Telegram automatically on startup via `bot.set_my_commands()`.

## Notifications

If `TG_NOTIFY_CHAT_ID` is configured, the bot sends a message to that chat whenever a proxy changes status **during operation**:

- Proxy came back online → `✅ Прокси онлайн: <name> (<host>:<port>)\nЗадержка: <N>ms`
- Proxy went dead → `💀 Прокси мертв: <name> (<host>:<port>)\nОшибок подряд: <N>`

Notifications are **not** sent on startup when proxies are first health-checked (no previous status = no notification).

## `TG_BOT_PROXY`

If Telegram is blocked on the server, set `TG_BOT_PROXY` to route bot API requests through an existing SOCKS5 proxy:

```env
TG_BOT_PROXY=socks5://127.0.0.1:10800
```
