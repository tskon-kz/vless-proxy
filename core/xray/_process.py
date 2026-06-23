import asyncio
import logging
import os
import signal

from config import settings
from core.parser import VlessConfig
from core.storage import Storage
from core.xray._config import write_xray_config

logger = logging.getLogger(__name__)


class XrayProcess:
    def __init__(self, proxy_id: int, local_port: int, config_path: str, storage: Storage) -> None:
        self._proxy_id = proxy_id
        self._local_port = local_port
        self._config_path = config_path
        self._storage = storage
        self._proc: asyncio.subprocess.Process | None = None
        self._pid: int | None = None

    @property
    def local_port(self) -> int:
        return self._local_port

    async def start(self) -> int:
        proc = await asyncio.create_subprocess_exec(
            settings.XRAY_BINARY, "run", "-config", self._config_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._proc = proc
        self._pid = proc.pid
        logger.info("xray started: proxy_id=%d local_port=%d pid=%d", self._proxy_id, self._local_port, self._pid)
        asyncio.create_task(self._monitor())
        return proc.pid

    async def _monitor(self) -> None:
        if self._proc is None:
            return
        await self._proc.wait()
        logger.warning(
            "xray process exited: proxy_id=%d local_port=%d pid=%d returncode=%s",
            self._proxy_id, self._local_port, self._pid, self._proc.returncode,
        )
        await self._storage.set_process_pid(self._proxy_id, self._local_port, None, "crashed")

    async def stop(self) -> None:
        if self._proc is None or self._proc.returncode is not None:
            return
        logger.info("stopping xray: proxy_id=%d local_port=%d pid=%d", self._proxy_id, self._local_port, self._pid)
        try:
            self._proc.send_signal(signal.SIGTERM)
            await asyncio.wait_for(self._proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("xray did not exit after SIGTERM, sending SIGKILL: pid=%d", self._pid)
            self._proc.kill()
            await self._proc.wait()

        if os.path.exists(self._config_path):
            os.remove(self._config_path)


class XrayProcessPool:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage
        self._processes: dict[int, XrayProcess] = {}

    async def start_proxy(self, proxy_id: int, config: VlessConfig, port: int | None = None) -> XrayProcess | None:
        if port is None:
            port = await self._storage.get_available_port()
        if port is None:
            logger.warning("no available port in pool for proxy_id=%d", proxy_id)
            return None

        config_path = write_xray_config(config, port, settings.XRAY_CONFIG_DIR)
        await self._storage.upsert_process(proxy_id, port, config_path)

        proc = XrayProcess(proxy_id, port, config_path, self._storage)
        pid = await proc.start()
        await self._storage.set_process_pid(proxy_id, port, pid, "running")

        self._processes[proxy_id] = proc
        return proc

    async def stop_proxy(self, proxy_id: int) -> None:
        proc = self._processes.pop(proxy_id, None)
        if proc is None:
            return
        await proc.stop()
        await self._storage.set_process_pid(proxy_id, proc.local_port, None, "stopped")

    async def stop_all(self) -> None:
        for proxy_id in list(self._processes):
            await self.stop_proxy(proxy_id)

    def get_process(self, proxy_id: int) -> XrayProcess | None:
        return self._processes.get(proxy_id)

    def get_all_ports(self) -> dict[int, int]:
        return {proxy_id: proc.local_port for proxy_id, proc in self._processes.items()}
