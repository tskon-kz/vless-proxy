from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot import strings
from bot.bot import AccessMiddleware, create_bot, process_links
from core.manager import UpdateReport


# ---------------------------------------------------------------------------
# strings.py
# ---------------------------------------------------------------------------

class TestStrings:
    def test_processing_count(self):
        text = strings.processing(5)
        assert "5" in text
        assert "🔄" in text

    def test_update_result_no_errors(self):
        text = strings.update_result(total=3, valid=3, invalid=0, errors=[])
        assert "3" in text
        assert "✅" in text
        assert "Ошибки" not in text

    def test_update_result_with_errors(self):
        text = strings.update_result(total=2, valid=1, invalid=1, errors=["bad UUID"])
        assert "❌ Ошибки:" in text
        assert "bad UUID" in text

    def test_status_message_empty_pool(self):
        text = strings.status_message(active=0, dead=0, pending=0, invalid=0, proxies=[])
        assert "✅ Активных: 0" in text
        assert "linkedin.com" in text

    def test_status_message_with_proxies(self):
        proxies = [
            {"name": "Amsterdam", "local_port": 10801, "latency_ms": 142},
            {"name": "Frankfurt", "local_port": 10802, "latency_ms": None},
        ]
        text = strings.status_message(active=2, dead=0, pending=0, invalid=0, proxies=proxies)
        assert "Amsterdam" in text
        assert "10801" in text
        assert "142ms" in text
        assert "—" in text  # None latency shown as dash

    def test_status_message_interval_minutes(self):
        with patch("bot.strings.settings") as s:
            s.CHECK_INTERVAL = 300
            s.CHECK_URL = "https://www.linkedin.com"
            text = strings.status_message(0, 0, 0, 0, [])
        assert "5 мин" in text

    def test_domain_extraction(self):
        assert strings._domain("https://www.linkedin.com") == "www.linkedin.com"
        assert strings._domain("http://example.com/path") == "example.com"


# ---------------------------------------------------------------------------
# AccessMiddleware
# ---------------------------------------------------------------------------

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
            result = await middleware(handler, message, {})

        handler.assert_not_called()


# ---------------------------------------------------------------------------
# process_links
# ---------------------------------------------------------------------------

VALID_URI = (
    "vless://9d507afd-7e90-4b7e-8bd8-6877f7a304ae@1.2.3.4:443"
    "?security=reality&sni=x.com&pbk=key&sid=s1"
)


class TestProcessLinks:
    async def test_no_vless_lines_does_nothing(self):
        message = MagicMock()
        message.answer = AsyncMock()
        manager = MagicMock()
        manager.update_proxies = AsyncMock()

        await process_links(message, "hello\nno vless here", manager)

        message.answer.assert_not_called()
        manager.update_proxies.assert_not_called()

    async def test_sends_processing_then_result(self):
        message = MagicMock()
        message.answer = AsyncMock()
        manager = MagicMock()
        manager.update_proxies = AsyncMock(return_value=UpdateReport(
            total_received=1, valid=1, invalid=0,
            parse_errors=[], newly_added=1, already_known=0,
            removed=0, source="telegram",
        ))

        await process_links(message, VALID_URI, manager)

        assert message.answer.call_count == 2
        first_call_text = message.answer.call_args_list[0][0][0]
        assert "🔄" in first_call_text
        second_call_text = message.answer.call_args_list[1][0][0]
        assert "✅" in second_call_text

    async def test_passes_lines_to_manager(self):
        message = MagicMock()
        message.answer = AsyncMock()
        manager = MagicMock()
        manager.update_proxies = AsyncMock(return_value=UpdateReport(
            total_received=1, valid=1, invalid=0,
            parse_errors=[], newly_added=1, already_known=0,
            removed=0, source="telegram",
        ))

        text = f"{VALID_URI}\nnot-a-link\n{VALID_URI}"
        await process_links(message, text, manager)

        call_args = manager.update_proxies.call_args
        links = call_args[0][0]
        # Only vless:// lines, duplicates included (dedup happens in manager)
        assert all(l.startswith("vless://") for l in links)
        assert call_args.kwargs.get("source") == "telegram"

    async def test_errors_shown_in_result(self):
        message = MagicMock()
        message.answer = AsyncMock()
        manager = MagicMock()
        manager.update_proxies = AsyncMock(return_value=UpdateReport(
            total_received=2, valid=1, invalid=1,
            parse_errors=["invalid UUID: 'bad'"],
            newly_added=1, already_known=0,
            removed=0, source="telegram",
        ))

        text = f"{VALID_URI}\nvless://bad@host:443?security=none"
        await process_links(message, text, manager)

        result_text = message.answer.call_args_list[1][0][0]
        assert "invalid UUID" in result_text


# ---------------------------------------------------------------------------
# create_bot
# ---------------------------------------------------------------------------

class TestCreateBot:
    def test_returns_bot_and_dispatcher(self):
        with patch("bot.bot.settings") as s, \
             patch("bot.bot.Bot") as MockBot, \
             patch("bot.bot.Dispatcher") as MockDp:
            s.TG_BOT_TOKEN = "123:token"
            s.TG_ALLOWED_USER_IDS = []
            s.TG_NOTIFY_CHAT_ID = None

            mock_dp = MagicMock()
            MockDp.return_value = mock_dp

            manager = MagicMock()
            manager.notify_callback = None

            bot, dp = create_bot(manager)

        assert bot is MockBot.return_value
        assert dp is mock_dp

    def test_notify_callback_set_when_chat_id_configured(self):
        with patch("bot.bot.settings") as s, \
             patch("bot.bot.Bot"), \
             patch("bot.bot.Dispatcher") as MockDp:
            s.TG_BOT_TOKEN = "123:token"
            s.TG_ALLOWED_USER_IDS = []
            s.TG_NOTIFY_CHAT_ID = 42

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

            MockDp.return_value = MagicMock()

            manager = MagicMock()
            manager.notify_callback = None

            create_bot(manager)

        assert manager.notify_callback is None
