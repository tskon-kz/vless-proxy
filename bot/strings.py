from core.storage import DownStat
from config import settings

START = (
    "👋 VLESS Proxy Manager\n\n"
    "Команды:\n"
    "/status — состояние пула прокси\n"
    "/check — принудительная проверка всех серверов\n"
    "/help — справка"
)

HELP = (
    "📋 Подписки задаются через переменную SUBSCRIPTION_URLS в .env\n\n"
    "Сервис автоматически обновляет список серверов каждые 30 минут.\n"
    "Живые сервера доступны через HTTP API:\n"
    "  GET /proxy/best  — самый быстрый\n"
    "  GET /proxy/list  — все активные"
)

CHECK_STARTED = "🔄 Запускаю проверку всех серверов..."


def status_message(
    active: int,
    dead: int,
    pending: int,
    proxies: list[dict],
) -> str:
    lines = [
        "📊 Состояние пула\n",
        f"✅ Активных: {active}",
        f"💀 Мёртвых: {dead}",
        f"⏳ Ожидают проверки: {pending}",
    ]
    if proxies:
        lines.append("\n🔌 Активные прокси:")
        for p in proxies:
            latency = f"{p['latency_ms']}ms" if p.get("latency_ms") is not None else "—"
            lines.append(f"• {p['name'] or p['host']} — порт {p['local_port']}, {latency}")
    interval_min = settings.CHECK_INTERVAL // 60
    lines.append(f"\n⏱ Интервал проверок: {interval_min} мин")
    return "\n".join(lines)


def proxy_alive(name: str, host: str, port: int, latency_ms: int | None) -> str:
    latency = f"{latency_ms}ms" if latency_ms is not None else "—"
    return f"✅ Прокси онлайн: {name or host} ({host}:{port})\nЗадержка: {latency}"


def proxy_dead(name: str, host: str, port: int, fail_count: int) -> str:
    return f"💀 Прокси мертв: {name or host} ({host}:{port})\nОшибок подряд: {fail_count}"


def _fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}с"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}м {secs}с" if secs else f"{minutes}м"
    hours, mins = divmod(minutes, 60)
    return f"{hours}ч {mins}м" if mins else f"{hours}ч"


def _fmt_section(stats: list[DownStat]) -> str:
    if not stats:
        return "  нет данных"
    lines = []
    for s in stats:
        label = s.proxy_name or s.proxy_host
        times = f"{s.down_count} раз" if s.down_count != 1 else "1 раз"
        downtime = _fmt_duration(s.total_downtime_s)
        lines.append(f"  • {label} — {times}, downtime {downtime}")
    return "\n".join(lines)


def down_stats_message(day: list[DownStat], week: list[DownStat]) -> str:
    return (
        "📉 Статистика падений\n\n"
        f"За 24 часа:\n{_fmt_section(day)}\n\n"
        f"За 7 дней:\n{_fmt_section(week)}"
    )
