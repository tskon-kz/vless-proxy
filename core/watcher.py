import asyncio
import hashlib
import logging
from pathlib import Path

from config import settings
from core.manager import ProxyManager

logger = logging.getLogger(__name__)


class FileWatcher:
    def __init__(self, manager: ProxyManager) -> None:
        self._manager = manager
        self._file_path = Path(settings.VLESS_FILE)
        self._last_hash: str | None = None
        self._check_interval = settings.FILE_CHECK_INTERVAL

    def _hash_file(self, path: Path) -> str | None:
        try:
            data = path.read_bytes()
            return hashlib.sha256(data).hexdigest()
        except FileNotFoundError:
            return None

    async def _check_file(self) -> None:
        current_hash = self._hash_file(self._file_path)

        if current_hash is None:
            return

        if current_hash == self._last_hash:
            return

        try:
            content = self._file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return

        if not content.strip():
            return  # file is empty — wait for content to appear

        self._last_hash = current_hash
        logger.info("file changed: %s", self._file_path)

        try:
            vless_links = [
                line.strip()
                for line in content.splitlines()
                if line.strip().startswith("vless://")
            ]

            if not vless_links:
                logger.warning(
                    "file %s contains no vless:// links, skipping", self._file_path
                )
                return

            report = await self._manager.update_proxies(vless_links, source="file")
            logger.info(
                "file update done: %d valid, %d invalid, %d added, %d removed",
                report.valid,
                report.invalid,
                report.newly_added,
                report.removed,
            )
            self._file_path.unlink()
            self._last_hash = None
            logger.info("deleted %s after import", self._file_path)

        except Exception as exc:
            logger.error("error processing file %s: %s", self._file_path, exc)

    async def load_once(self) -> bool:
        if not self._file_path.exists():
            return False

        content = self._file_path.read_text(encoding="utf-8", errors="replace")
        if not content.strip():
            return False  # empty file — wait for content

        links = [
            line.strip()
            for line in content.splitlines()
            if line.strip().startswith("vless://")
        ]

        if not links:
            return False

        await self._manager.update_proxies(links, source="file")
        self._file_path.unlink()
        logger.info("loaded and deleted %s", self._file_path)
        return True

    async def run_forever(self) -> None:
        logger.info("file watcher started, watching: %s", self._file_path)

        if self._file_path.exists():
            await self._check_file()

        while True:
            await asyncio.sleep(self._check_interval)
            await self._check_file()
