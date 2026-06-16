from config import settings

START = (
    "👋 VLESS Proxy Manager\n\n"
    "Команды:\n"
    "/status — состояние пула прокси\n"
    "/check — принудительная проверка всех серверов\n"
    "/sub_add <url> [название] — добавить подписку\n"
    "/sub_list — список подписок\n"
    "/sub_refresh [id] — обновить подписку (или все)\n"
    "/sub_remove <id> — удалить подписку\n"
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


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------

SUB_ADD_USAGE = "Укажите URL подписки: /sub_add <url> [название]"
SUB_ADD_INVALID_URL = "URL должен начинаться с http:// или https://"
SUB_ADDING = "🔄 Добавляю подписку..."
SUB_REFRESHING = "🔄 Обновляю подписки..."
SUB_LIST_EMPTY = "Нет добавленных подписок."
SUB_REMOVE_USAGE = "Укажите ID подписки: /sub_remove <id>"
SUB_REMOVE_USAGE_CONFIRM = "Для подтверждения: /sub_remove <id> confirm"
SUB_ID_INVALID = "ID подписки должен быть числом."
SUB_REFRESH_USAGE = "Формат: /sub_refresh [id]"


def sub_added(sub_id: int, name: str, url: str, count: int) -> str:
    label = name or _domain(url)
    return (
        f"✅ Подписка добавлена: {label}\n"
        f"ID: {sub_id}\n"
        f"Загружено ссылок: {count}\n"
        "Запущена проверка живости..."
    )


def sub_add_error(url: str, error: str) -> str:
    return f"❌ Не удалось загрузить подписку {_domain(url)}: {error}"


def sub_not_found(sub_id: int) -> str:
    return f"Подписка #{sub_id} не найдена."


def sub_list(subs) -> str:
    lines = ["📋 Подписки:\n"]
    for s in subs:
        label = s.name or _domain(s.url)
        status = f"✅{s.active} / ⏳{s.pending} / 💀{s.dead}"
        lines.append(f"#{s.id} {label} — {status}")
        if s.last_fetch:
            import time as _time
            ago = int((_time.time() - s.last_fetch) / 60)
            lines.append(f"   Обновлено: {ago} мин назад")
        else:
            lines.append("   Ещё не обновлялась")
    return "\n".join(lines)


def sub_refresh_result(results) -> str:
    lines = ["🔄 Результат обновления подписок:\n"]
    for r in results:
        domain = _domain(r.url)
        if r.success:
            lines.append(f"✅ {domain}: {r.count} ссылок")
        else:
            lines.append(f"❌ {domain}: {r.error}")
    return "\n".join(lines)


def sub_refresh_one_result(result) -> str:
    domain = _domain(result.url)
    if result.success:
        return f"✅ Подписка {domain} обновлена: {result.count} ссылок"
    return f"❌ Не удалось обновить {domain}: {result.error}"


def sub_remove_confirm(sub_id: int, name: str, url: str, total: int) -> str:
    label = name or _domain(url)
    return (
        f"⚠️ Удалить подписку #{sub_id} «{label}»?\n"
        f"Будет удалено прокси: {total}\n\n"
        f"Подтвердите: /sub_remove {sub_id} confirm"
    )


def sub_removed(sub_id: int, name: str, url: str) -> str:
    label = name or _domain(url)
    return f"🗑 Подписка #{sub_id} «{label}» удалена."
