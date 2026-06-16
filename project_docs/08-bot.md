# Модуль 8: Telegram бот

## Задача

Реализовать `bot/bot.py` — основной интерфейс управления сервисом. Принимает VLESS ссылки, отдаёт статус, запускает принудительные проверки. Доступ только для пользователей из `TG_ALLOWED_USER_IDS`.

## Что реализовать

### Команды

**`/start`**

```
👋 VLESS Proxy Manager

Команды:
/status — состояние пула прокси
/check — принудительная проверка всех серверов
/help — справка по формату ссылок

Для обновления списка — отправьте ссылки vless:// текстом или файлом.
```

**`/status`**

Запросить `manager.get_status()` и отформатировать:

```
📊 Состояние пула

✅ Активных: 5
💀 Мёртвых: 2
⏳ Ожидают проверки: 0
❌ Невалидных: 1

🔌 Активные прокси:
• Amsterdam — порт 10801, 142ms
• Frankfurt — порт 10802, 98ms
• Rotterdam — порт 10803, 201ms
• Stockholm — порт 10804, 315ms
• Warsaw — порт 10805, 178ms

🔍 Проверочный URL: linkedin.com
⏱ Интервал проверок: 5 мин
```

**`/check`**

```
🔄 Запускаю проверку всех серверов...
```
Вызвать `manager.force_recheck()` (не блокировать — fire and forget). Сразу ответить, не ждать результата.

**`/help`**

```
📋 Формат ссылок

Отправьте список VLESS ссылок — каждая с новой строки:

vless://uuid@host:port?params#name
vless://uuid@host:port?params#name

Или прикрепите .txt файл с ссылками.

⚠️ Новый список полностью заменяет старый.
Все текущие прокси будут перепроверены.
```

### Обработка ссылок

Основная функциональность — обработка входящих сообщений с VLESS ссылками.

**Текстовое сообщение со ссылками:**

Любое сообщение содержащее хотя бы одну строку начинающуюся с `vless://` — интерпретировать как список ссылок для обновления.

```
Получено ссылок: 8
🔄 Обрабатываю...
```

После обработки:
```
✅ Обновление завершено

Получено: 8
Валидных: 7
Невалидных: 1

❌ Ошибки:
• vless://bad-uuid@... — невалидный UUID

Запущена проверка живости...
Результат появится в /status через ~30 сек
```

**Файл `.txt` или без расширения:**

Скачать через `bot.download()`, прочитать как текст, обработать так же как текстовое сообщение.

```python
@router.message(F.document)
async def handle_document(message: Message, bot: Bot, manager: ProxyManager):
    doc = message.document
    if doc.mime_type not in ("text/plain", None) and not doc.file_name.endswith(".txt"):
        await message.reply("❌ Поддерживаются только .txt файлы")
        return
    file = await bot.download(doc.file_id)
    content = file.read().decode("utf-8", errors="replace")
    await process_links(message, content, manager)
```

### Middleware: проверка доступа

```python
@router.message()
async def check_access(message: Message, handler, data):
    if message.from_user.id not in settings.TG_ALLOWED_USER_IDS:
        # Молча игнорировать — не сообщать что бот существует
        return
    return await handler(message, data)
```

Использовать `BaseMiddleware` aiogram 3.x.

### Уведомления о смене статуса (опционально)

Если задан `TG_NOTIFY_CHAT_ID` в конфиге — отправлять сообщение когда сервер умирает или оживает:

```
💀 Прокси умер: Amsterdam (155.117.137.168:443)
Ошибок подряд: 3
```

```
✅ Прокси ожил: Amsterdam (155.117.137.168:443)
Задержка: 142ms
```

Для этого `ProxyManager._on_health_change` должен вызывать callback из бота.

### Добавить в `config.py`

```
TG_NOTIFY_CHAT_ID   — chat_id для уведомлений, дефолт: None (отключено)
```

### Factory функция

```python
def create_bot(manager: ProxyManager) -> tuple[Bot, Dispatcher]:
    bot = Bot(token=settings.TG_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    dp["manager"] = manager   # dependency injection через dp storage
    return bot, dp
```

Запуск в `main.py`:
```python
bot, dp = create_bot(manager)
asyncio.create_task(dp.start_polling(bot, allowed_updates=["message"]))
```

## Что НЕ нужно

- Inline кнопки и keyboards — только текстовые команды
- Webhook режим — только polling
- Хранение истории сообщений
- `/add` и `/remove` для отдельных ссылок — только полная замена списка
