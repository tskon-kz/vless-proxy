# Модуль 9: файловый watcher (fallback)

## Задача

Реализовать `watcher/file_watcher.py` — альтернативный способ обновления ссылок через файл на диске. Работает независимо от Telegram. Нужен для случаев когда:
- Telegram заблокирован или недоступен
- бот упал
- нужна автоматизация через cron/скрипты
- первоначальная загрузка ссылок при деплое

## Механизм работы

Watcher следит за файлом `settings.VLESS_FILE` (дефолт: `./vless.txt`). При изменении файла — читает его и вызывает `manager.update_proxies()`.

Изменение определяется по **хешу содержимого** (MD5 или sha256), не по mtime — mtime может меняться без изменения содержимого (например при `touch`).

## Что реализовать

### Класс `FileWatcher`

```python
class FileWatcher:
    def __init__(self, manager: ProxyManager):
        self._manager = manager
        self._file_path = Path(settings.VLESS_FILE)
        self._last_hash: str | None = None
        self._check_interval = settings.FILE_CHECK_INTERVAL

    async def run_forever(self) -> None:
        """Основной цикл опроса файла."""

    async def _check_file(self) -> None:
        """Проверить файл на изменения, обновить прокси если изменился."""

    def _hash_file(self, path: Path) -> str | None:
        """Вернуть sha256 содержимого файла или None если файл не существует."""

    async def load_once(self) -> bool:
        """Прочитать файл прямо сейчас, без ожидания изменений. Вернуть True если файл существует."""
```

### Логика `run_forever`

```python
async def run_forever(self) -> None:
    logging.info(f"File watcher started, watching: {self._file_path}")

    # Первый запуск — загрузить файл если существует
    if self._file_path.exists():
        await self._check_file()

    while True:
        await asyncio.sleep(self._check_interval)
        await self._check_file()
```

### Логика `_check_file`

```python
async def _check_file(self) -> None:
    current_hash = self._hash_file(self._file_path)

    if current_hash is None:
        # файл не существует — не трогать текущий пул
        return

    if current_hash == self._last_hash:
        # файл не изменился
        return

    # файл изменился — обработать
    logging.info(f"File changed: {self._file_path}")
    self._last_hash = current_hash

    try:
        content = self._file_path.read_text(encoding="utf-8", errors="replace")
        lines = [line.strip() for line in content.splitlines()]
        vless_links = [l for l in lines if l.startswith("vless://")]

        if not vless_links:
            logging.warning(f"File {self._file_path} contains no vless:// links, skipping")
            return

        report = await self._manager.update_proxies(vless_links, source="file")
        logging.info(
            f"File update done: {report.valid} valid, "
            f"{report.invalid} invalid, "
            f"{report.newly_added} added, "
            f"{report.removed} removed"
        )

    except Exception as e:
        logging.error(f"Error processing file {self._file_path}: {e}")
```

### Формат файла `vless.txt`

Файл простой — каждая строка это одна ссылка. Строки начинающиеся с `#` — комментарии, игнорируются. Пустые строки игнорируются.

```
# Нидерланды
vless://9d507afd-7e90-4b7e-8bd8-6877f7a304ae@155.117.137.168:443?flow=xtls-rprx-vision&type=tcp&security=reality&pbk=CMkW...&sni=yahoo.com&sid=7e77e7e2#Amsterdam

# Германия
vless://a1b2c3d4-...@192.168.1.1:443?...#Frankfurt

# Временно отключён
# vless://dead-server-uuid@dead.host:443?...#Dead Server
```

Создать `vless.txt.example` с таким форматом и добавить в репозиторий. Сам `vless.txt` добавить в `.gitignore`.

### Метод `load_once`

Используется в `main.py` при старте — загрузить файл один раз немедленно, до запуска polling loop:

```python
async def load_once(self) -> bool:
    if not self._file_path.exists():
        logging.info(f"No file found at {self._file_path}, skipping initial load")
        return False

    self._last_hash = self._hash_file(self._file_path)
    content = self._file_path.read_text(encoding="utf-8", errors="replace")
    links = [l.strip() for l in content.splitlines()
             if l.strip().startswith("vless://")]

    if not links:
        return False

    await self._manager.update_proxies(links, source="file")
    return True
```

### Интеграция в `main.py`

```python
watcher = FileWatcher(manager)

# При старте — загрузить файл если есть
await watcher.load_once()

# Запустить фоновый watcher
asyncio.create_task(watcher.run_forever())
```

## Как обновлять ссылки через файл

### Вариант 1: вручную

```bash
# Открыть файл и вставить ссылки
nano /opt/vless-manager/vless.txt

# Сервис подхватит через 30 секунд (FILE_CHECK_INTERVAL)
# Или можно touch для гарантированного тригера:
# НЕТ — touch не меняет хеш, используйте настоящее редактирование
```

### Вариант 2: через скрипт

```bash
#!/bin/bash
# update-proxies.sh — принимает ссылки из stdin или аргументов
VLESS_FILE="/opt/vless-manager/vless.txt"

if [ -p /dev/stdin ]; then
    cat > "$VLESS_FILE"
else
    echo "$@" | tr ' ' '\n' > "$VLESS_FILE"
fi

echo "Updated $VLESS_FILE, watcher will pick up in ${FILE_CHECK_INTERVAL:-30}s"
```

### Вариант 3: через cron (обновление с внешнего источника)

```bash
# crontab -e
*/10 * * * * curl -s https://your-subscription-url/vless.txt > /opt/vless-manager/vless.txt
```

Добавить пример скрипта `scripts/update-proxies.sh` в репозиторий.

## Что НЕ нужно

- `watchdog` библиотека — простой polling через asyncio.sleep достаточен
- Поддержка нескольких файлов
- Рекурсивный watch директории
- Обработка переименований файла
