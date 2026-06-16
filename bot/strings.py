from config import settings

START = (
    "👋 VLESS Proxy Manager\n\n"
    "Команды:\n"
    "/status — состояние пула прокси\n"
    "/check — принудительная проверка всех серверов\n"
    "/help — справка по формату ссылок\n\n"
    "Для обновления списка — отправьте ссылки vless:// текстом или файлом."
)

HELP = (
    "📋 Формат ссылок\n\n"
    "Отправьте список VLESS ссылок — каждая с новой строки:\n\n"
    "vless://uuid@host:port?params#name\n"
    "vless://uuid@host:port?params#name\n\n"
    "Или прикрепите .txt файл с ссылками.\n\n"
    "⚠️ Новый список полностью заменяет старый.\n"
    "Все текущие прокси будут перепроверены."
)

CHECK_STARTED = "🔄 Запускаю проверку всех серверов..."

FILE_UNSUPPORTED = "❌ Поддерживаются только .txt файлы"


def processing(count: int) -> str:
    return f"Получено ссылок: {count}\n🔄 Обрабатываю..."


def update_result(
    total: int,
    valid: int,
    invalid: int,
    errors: list[str],
) -> str:
    lines = [
        "✅ Обновление завершено\n",
        f"Получено: {total}",
        f"Валидных: {valid}",
        f"Невалидных: {invalid}",
    ]
    if errors:
        lines.append("\n❌ Ошибки:")
        for e in errors:
            lines.append(f"• {e}")
    lines.append("\nЗапущена проверка живости...")
    lines.append("Результат появится в /status через ~30 сек")
    return "\n".join(lines)


def status_message(
    active: int,
    dead: int,
    pending: int,
    invalid: int,
    proxies: list[dict],
) -> str:
    lines = [
        "📊 Состояние пула\n",
        f"✅ Активных: {active}",
        f"💀 Мёртвых: {dead}",
        f"⏳ Ожидают проверки: {pending}",
        f"❌ Невалидных: {invalid}",
    ]
    if proxies:
        lines.append("\n🔌 Активные прокси:")
        for p in proxies:
            latency = f"{p['latency_ms']}ms" if p.get("latency_ms") is not None else "—"
            lines.append(f"• {p['name']} — порт {p['local_port']}, {latency}")
    lines.append(f"\n🔍 Проверочный URL: {_domain(settings.CHECK_URL)}")
    interval_min = settings.CHECK_INTERVAL // 60
    lines.append(f"⏱ Интервал проверок: {interval_min} мин")
    return "\n".join(lines)


def proxy_alive(name: str, host: str, port: int, latency_ms: int | None) -> str:
    latency = f"{latency_ms}ms" if latency_ms is not None else "—"
    return f"✅ Прокси ожил: {name} ({host}:{port})\nЗадержка: {latency}"


def proxy_dead(name: str, host: str, port: int, fail_count: int) -> str:
    return f"💀 Прокси умер: {name} ({host}:{port})\nОшибок подряд: {fail_count}"


def _domain(url: str) -> str:
    return url.removeprefix("https://").removeprefix("http://").split("/")[0]
