# Telegram-бот (`bot/bot.py`, `bot/strings.py`)

## Создание бота

```python
from bot.bot import create_bot
bot, dp = create_bot(manager)
await dp.start_polling(bot, allowed_updates=["message"])
```

`create_bot` возвращает `(Bot, Dispatcher)`. `manager` инжектируется в хендлеры через `dp["manager"] = manager`.

## Доступ

Все сообщения проходят через `AccessMiddleware`. Бот молча игнорирует сообщения от пользователей не из `TG_ALLOWED_USER_IDS` — нет ни ошибок, ни ответов.

## Команды

| Команда | Что делает |
|---------|-----------|
| `/start` | Приветствие и список команд |
| `/help` | Объяснение формата ссылок |
| `/status` | Состояние пула: счётчики + список активных прокси с портами и задержкой |
| `/check` | Запустить немедленную проверку всех прокси (`manager.force_recheck()`) |

## Добавление прокси

**Текстом** — если сообщение содержит `vless://`, извлекаются все ссылки из текста и передаются в `manager.update_proxies(source="telegram")`.

**Файлом** — принимаются `.txt` файлы и файлы без расширения (`mime_type=None`). Содержимое обрабатывается как текст. Другие форматы отклоняются с сообщением об ошибке.

Оба способа показывают отчёт: сколько получено, валидных, невалидных. После этого запускается проверка живости в фоне.

## Уведомления о смене статуса

Если `TG_NOTIFY_CHAT_ID` задан, `create_bot` устанавливает `manager.notify_callback`. При каждой смене статуса прокси в чат отправляется сообщение:

- Прокси ожил: имя, хост, задержка
- Прокси умер: имя, хост, счётчик ошибок подряд

## Строки (`bot/strings.py`)

Весь пользовательский текст вынесен в `bot/strings.py`. Менеджер и другие модули не содержат строк на русском — только `strings.py` и `parser.py` (сводка ошибок).

Публичный интерфейс:

```python
START: str                    # приветствие
HELP: str                     # справка по формату
CHECK_STARTED: str            # "запускаю проверку..."
FILE_UNSUPPORTED: str         # ошибка при неверном формате файла

processing(count) → str
update_result(total, valid, invalid, errors) → str
status_message(active, dead, pending, invalid, proxies) → str
proxy_alive(name, host, port, latency_ms) → str    # уведомление
proxy_dead(name, host, port, fail_count) → str     # уведомление
```
