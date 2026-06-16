import logging
from typing import Any, Awaitable, Callable

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command
from aiogram.types import Message

from bot import strings
from config import settings
from core.manager import ProxyManager

logger = logging.getLogger(__name__)

router = Router()


# ---------------------------------------------------------------------------
# Access middleware
# ---------------------------------------------------------------------------

class AccessMiddleware:
    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        if not event.from_user or event.from_user.id not in settings.TG_ALLOWED_USER_IDS:
            return
        return await handler(event, data)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(strings.START)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(strings.HELP)


@router.message(Command("check"))
async def cmd_check(message: Message, manager: ProxyManager) -> None:
    await message.answer(strings.CHECK_STARTED)
    await manager.force_recheck()


@router.message(Command("status"))
async def cmd_status(message: Message, manager: ProxyManager) -> None:
    status = await manager.get_status()
    proxies = [
        {
            "name": p.name or p.host,
            "local_port": p.local_port,
            "latency_ms": p.latency_ms,
        }
        for p in status.active_proxies
    ]
    pool = status.pool_stats
    text = strings.status_message(
        active=pool.active,
        dead=pool.dead,
        pending=pool.pending,
        invalid=pool.invalid,
        proxies=proxies,
    )
    await message.answer(text)


# ---------------------------------------------------------------------------
# Link processing
# ---------------------------------------------------------------------------

async def process_links(message: Message, text: str, manager: ProxyManager) -> None:
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith("vless://")]
    if not lines:
        return

    await message.answer(strings.processing(len(lines)))

    report = await manager.update_proxies(lines, source="telegram")

    await message.answer(
        strings.update_result(
            total=report.total_received,
            valid=report.valid,
            invalid=report.invalid,
            errors=report.parse_errors,
        )
    )


@router.message(F.text & F.text.contains("vless://"))
async def handle_links(message: Message, manager: ProxyManager) -> None:
    await process_links(message, message.text, manager)


@router.message(Command("sub_add"))
async def cmd_sub_add(message: Message, manager: ProxyManager) -> None:
    if manager.subscription_manager is None:
        return
    text = message.text or ""
    parts = text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer(strings.SUB_ADD_USAGE)
        return
    url = parts[1]
    name = parts[2] if len(parts) > 2 else ""
    if not url.startswith(("http://", "https://")):
        await message.answer(strings.SUB_ADD_INVALID_URL)
        return
    await message.answer(strings.SUB_ADDING)
    try:
        sub_id, result = await manager.subscription_manager.add_subscription(url, name)
        if result.success:
            await message.answer(strings.sub_added(sub_id, name, url, result.count))
        else:
            await message.answer(strings.sub_add_error(url, result.error))
    except Exception as exc:
        await message.answer(strings.sub_add_error(url, str(exc)))


@router.message(Command("sub_list"))
async def cmd_sub_list(message: Message, manager: ProxyManager) -> None:
    if manager.subscription_manager is None:
        return
    subs = await manager.subscription_manager.list_subscriptions()
    if not subs:
        await message.answer(strings.SUB_LIST_EMPTY)
        return
    await message.answer(strings.sub_list(subs))


@router.message(Command("sub_refresh"))
async def cmd_sub_refresh(message: Message, manager: ProxyManager) -> None:
    if manager.subscription_manager is None:
        return
    text = message.text or ""
    parts = text.split()
    await message.answer(strings.SUB_REFRESHING)
    if len(parts) < 2:
        results = await manager.subscription_manager.refresh_all()
        await message.answer(strings.sub_refresh_result(results))
        return
    try:
        sub_id = int(parts[1])
    except ValueError:
        await message.answer(strings.SUB_ID_INVALID)
        return
    sub = await manager.subscription_manager.get_subscription(sub_id)
    if sub is None:
        await message.answer(strings.sub_not_found(sub_id))
        return
    result = await manager.subscription_manager.refresh_subscription(sub_id)
    await message.answer(strings.sub_refresh_one_result(result))


@router.message(Command("sub_remove"))
async def cmd_sub_remove(message: Message, manager: ProxyManager) -> None:
    if manager.subscription_manager is None:
        return
    text = message.text or ""
    parts = text.split()
    if len(parts) < 2:
        await message.answer(strings.SUB_REMOVE_USAGE)
        return
    try:
        sub_id = int(parts[1])
    except ValueError:
        await message.answer(strings.SUB_ID_INVALID)
        return
    sub = await manager.subscription_manager.get_subscription(sub_id)
    if sub is None:
        await message.answer(strings.sub_not_found(sub_id))
        return
    confirmed = len(parts) > 2 and parts[2] == "confirm"
    if not confirmed:
        stats = await manager.storage.get_subscription_stats(sub_id)
        total = stats.total if stats else 0
        await message.answer(strings.sub_remove_confirm(sub_id, sub.name, sub.url, total))
        return
    await manager.remove_subscription(sub_id)
    await message.answer(strings.sub_removed(sub_id, sub.name, sub.url))


@router.message(F.document)
async def handle_document(message: Message, bot: Bot, manager: ProxyManager) -> None:
    doc = message.document
    is_txt = (
        doc.mime_type == "text/plain"
        or (doc.file_name and doc.file_name.endswith(".txt"))
        or doc.mime_type is None
    )
    if not is_txt:
        await message.reply(strings.FILE_UNSUPPORTED)
        return

    file = await bot.download(doc.file_id)
    content = file.read().decode("utf-8", errors="replace")
    await process_links(message, content, manager)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_bot(manager: ProxyManager) -> tuple[Bot, Dispatcher]:
    session = AiohttpSession(proxy=settings.TG_BOT_PROXY) if settings.TG_BOT_PROXY else None
    bot = Bot(token=settings.TG_BOT_TOKEN, session=session)
    dp = Dispatcher()
    dp.message.middleware(AccessMiddleware())
    dp.include_router(router)
    dp["manager"] = manager

    if settings.TG_NOTIFY_CHAT_ID:
        async def _notify(proxy, result) -> None:
            if result.success:
                text = strings.proxy_alive(proxy.name, proxy.host, proxy.port, result.latency_ms)
            else:
                text = strings.proxy_dead(proxy.name, proxy.host, proxy.port, proxy.fail_count + 1)
            await bot.send_message(settings.TG_NOTIFY_CHAT_ID, text)

        manager.notify_callback = _notify

    return bot, dp
