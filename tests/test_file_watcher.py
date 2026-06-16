from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.manager import UpdateReport
from watcher.file_watcher import FileWatcher

VALID_URI = (
    "vless://9d507afd-7e90-4b7e-8bd8-6877f7a304ae@1.2.3.4:443"
    "?security=reality&sni=x.com&pbk=key&sid=s1"
)


def _make_watcher(tmp_path: Path, file_name: str = "vless.txt") -> tuple[FileWatcher, MagicMock]:
    manager = MagicMock()
    manager.update_proxies = AsyncMock(return_value=UpdateReport(
        total_received=1, valid=1, invalid=0,
        parse_errors=[], newly_added=1, already_known=0,
        removed=0, source="file",
    ))
    with patch("watcher.file_watcher.settings") as s:
        s.VLESS_FILE = str(tmp_path / file_name)
        s.FILE_CHECK_INTERVAL = 30
        watcher = FileWatcher(manager)
    return watcher, manager


class TestHashFile:
    def test_returns_none_for_missing_file(self, tmp_path):
        watcher, _ = _make_watcher(tmp_path)
        result = watcher._hash_file(tmp_path / "nonexistent.txt")
        assert result is None

    def test_returns_string_for_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        watcher, _ = _make_watcher(tmp_path)
        result = watcher._hash_file(f)
        assert isinstance(result, str)
        assert len(result) == 64  # sha256 hex

    def test_same_content_same_hash(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("same content")
        f2.write_text("same content")
        watcher, _ = _make_watcher(tmp_path)
        assert watcher._hash_file(f1) == watcher._hash_file(f2)

    def test_different_content_different_hash(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("content A")
        watcher, _ = _make_watcher(tmp_path)
        hash_a = watcher._hash_file(f)
        f.write_text("content B")
        hash_b = watcher._hash_file(f)
        assert hash_a != hash_b

    def test_touch_does_not_change_hash(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("content")
        watcher, _ = _make_watcher(tmp_path)
        h1 = watcher._hash_file(f)
        f.touch()  # update mtime without changing content
        h2 = watcher._hash_file(f)
        assert h1 == h2


class TestCheckFile:
    async def test_skips_missing_file(self, tmp_path):
        watcher, manager = _make_watcher(tmp_path)
        await watcher._check_file()
        manager.update_proxies.assert_not_called()

    async def test_calls_update_on_first_check(self, tmp_path):
        watcher, manager = _make_watcher(tmp_path)
        (tmp_path / "vless.txt").write_text(VALID_URI)
        await watcher._check_file()
        manager.update_proxies.assert_called_once()

    async def test_skips_unchanged_file(self, tmp_path):
        watcher, manager = _make_watcher(tmp_path)
        f = tmp_path / "vless.txt"
        f.write_text(VALID_URI)
        await watcher._check_file()
        await watcher._check_file()
        assert manager.update_proxies.call_count == 1

    async def test_triggers_on_content_change(self, tmp_path):
        watcher, manager = _make_watcher(tmp_path)
        f = tmp_path / "vless.txt"
        f.write_text(VALID_URI)
        await watcher._check_file()

        uri2 = VALID_URI.replace("1.2.3.4", "5.6.7.8")
        f.write_text(f"{VALID_URI}\n{uri2}")
        await watcher._check_file()

        assert manager.update_proxies.call_count == 2

    async def test_skips_file_with_no_vless_links(self, tmp_path):
        watcher, manager = _make_watcher(tmp_path)
        (tmp_path / "vless.txt").write_text("# just a comment\n\nhello world")
        await watcher._check_file()
        manager.update_proxies.assert_not_called()

    async def test_ignores_comment_lines(self, tmp_path):
        watcher, manager = _make_watcher(tmp_path)
        content = f"# comment\n{VALID_URI}\n# another comment"
        (tmp_path / "vless.txt").write_text(content)
        await watcher._check_file()

        links = manager.update_proxies.call_args[0][0]
        assert all(not l.startswith("#") for l in links)
        assert len(links) == 1

    async def test_passes_source_file(self, tmp_path):
        watcher, manager = _make_watcher(tmp_path)
        (tmp_path / "vless.txt").write_text(VALID_URI)
        await watcher._check_file()
        assert manager.update_proxies.call_args.kwargs.get("source") == "file"

    async def test_handles_exception_gracefully(self, tmp_path):
        watcher, manager = _make_watcher(tmp_path)
        (tmp_path / "vless.txt").write_text(VALID_URI)
        manager.update_proxies.side_effect = RuntimeError("boom")
        # Should not raise
        await watcher._check_file()


class TestLoadOnce:
    async def test_returns_false_when_no_file(self, tmp_path):
        watcher, manager = _make_watcher(tmp_path)
        result = await watcher.load_once()
        assert result is False
        manager.update_proxies.assert_not_called()

    async def test_returns_false_when_no_vless_links(self, tmp_path):
        watcher, manager = _make_watcher(tmp_path)
        (tmp_path / "vless.txt").write_text("# empty\n")
        result = await watcher.load_once()
        assert result is False
        manager.update_proxies.assert_not_called()

    async def test_returns_true_and_calls_update(self, tmp_path):
        watcher, manager = _make_watcher(tmp_path)
        (tmp_path / "vless.txt").write_text(VALID_URI)
        result = await watcher.load_once()
        assert result is True
        manager.update_proxies.assert_called_once()

    async def test_sets_last_hash_so_run_forever_wont_double_load(self, tmp_path):
        watcher, manager = _make_watcher(tmp_path)
        (tmp_path / "vless.txt").write_text(VALID_URI)
        await watcher.load_once()
        # _check_file should see the same hash and skip
        await watcher._check_file()
        assert manager.update_proxies.call_count == 1
