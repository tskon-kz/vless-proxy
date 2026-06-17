from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot import strings
from bot.bot import AccessMiddleware, create_bot


class TestStrings:
    def test_status_message_empty_pool(self):
        with patch("bot.strings.settings") as s:
            s.CHECK_INTERVAL = 300
            text = strings.status_message(active=0, dead=0, pending=0, proxies=[])
        assert "✅ Активных: 0" in text
        assert "5 мин" in text

    def test_status_message_with_proxies(self):
        proxies = [
            {"name": "Amsterdam", "host": "1.2.3.4", "local_port": 10801, "latency_ms": 142},
            {"name": "", "host": "5.6.7.8", "local_port": 10802, "latency_ms": None},
        ]
        with patch("bot.strings.settings") as s:
            s.CHECK_INTERVAL = 300
            text = strings.status_message(active=2, dead=0, pending=0, proxies=proxies)
        assert "Amsterdam" in text
        assert "10801" in text
        assert "142ms" in text
        assert "—" in text

    def test_proxy_alive(self):
        text = strings.proxy_alive("Server", "1.2.3.4", 443, 55)
        assert "онлайн" in text
        assert "55ms" in text

    def test_proxy_dead(self):
        text = strings.proxy_dead("Server", "1.2.3.4", 443, 3)
        assert "мертв" in text
        assert "3" in text


class TestAccessMiddleware:
    async def test_allowed_user_passes(self):
        middleware = AccessMiddleware()
        handler = AsyncMock(return_value="ok")
        message = MagicMock()
        message.from_user.id = 123

        with patch("bot.bot.settings") as s:
            s.TG_ALLOWED_USER_IDS = [123, 456]
            result = await middleware(handler, message, {})

        handler.assert_called_once()
        assert result == "ok"

    async def test_unknown_user_blocked(self):
        middleware = AccessMiddleware()
        handler = AsyncMock()
        message = MagicMock()
        message.from_user.id = 999

        with patch("bot.bot.settings") as s:
            s.TG_ALLOWED_USER_IDS = [123]
            result = await middleware(handler, message, {})

        handler.assert_not_called()
        assert result is None

    async def test_no_from_user_blocked(self):
        middleware = AccessMiddleware()
        handler = AsyncMock()
        message = MagicMock()
        message.from_user = None

        with patch("bot.bot.settings") as s:
            s.TG_ALLOWED_USER_IDS = [123]
            await middleware(handler, message, {})

        handler.assert_not_called()


class TestCreateBot:
    def test_returns_bot_and_dispatcher(self):
        with patch("bot.bot.settings") as s, \
             patch("bot.bot.Bot") as MockBot, \
             patch("bot.bot.Dispatcher") as MockDp:
            s.TG_BOT_TOKEN = "123:token"
            s.TG_ALLOWED_USER_IDS = []
            s.TG_NOTIFY_CHAT_ID = None
            s.TG_BOT_PROXY = None

            MockDp.return_value = MagicMock()
            manager = MagicMock()
            manager.notify_callback = None

            bot, dp = create_bot(manager)

        assert bot is MockBot.return_value

    def test_notify_callback_set_when_chat_id_configured(self):
        with patch("bot.bot.settings") as s, \
             patch("bot.bot.Bot"), \
             patch("bot.bot.Dispatcher") as MockDp:
            s.TG_BOT_TOKEN = "123:token"
            s.TG_ALLOWED_USER_IDS = []
            s.TG_NOTIFY_CHAT_ID = 42
            s.TG_BOT_PROXY = None

            MockDp.return_value = MagicMock()
            manager = MagicMock()
            manager.notify_callback = None

            create_bot(manager)

        assert manager.notify_callback is not None

    def test_no_notify_callback_when_no_chat_id(self):
        with patch("bot.bot.settings") as s, \
             patch("bot.bot.Bot"), \
             patch("bot.bot.Dispatcher") as MockDp:
            s.TG_BOT_TOKEN = "123:token"
            s.TG_ALLOWED_USER_IDS = []
            s.TG_NOTIFY_CHAT_ID = None
            s.TG_BOT_PROXY = None

            MockDp.return_value = MagicMock()
            manager = MagicMock()
            manager.notify_callback = None

            create_bot(manager)

        assert manager.notify_callback is None
