import logging
from typing import Any, Awaitable, Callable

from aiogram import Bot, Dispatcher, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command
from aiogram.types import Message

from bot import strings
from config import settings
from core.manager import ProxyManager

logger = logging.getLogger(__name__)

router = Router()


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
            "name": p.name,
            "host": p.host,
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
        proxies=proxies,
    )
    await message.answer(text)


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
