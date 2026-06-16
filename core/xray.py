import asyncio
import json
import logging
import os
import signal

from config import settings
from core.parser import VlessConfig
from core.storage import Storage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------

def _build_stream_settings(config: VlessConfig) -> dict:
    security = config.security
    net = config.type

    if net == "ws":
        stream: dict = {
            "network": "ws",
            "security": security,
            "wsSettings": {
                "path": config.path,
                "headers": {"Host": config.host_header} if config.host_header else {},
            },
        }
        if security == "tls":
            stream["tlsSettings"] = _tls_settings(config)
        elif security == "reality":
            stream["realitySettings"] = _reality_settings(config)
        return stream

    if net == "grpc":
        stream = {
            "network": "grpc",
            "security": security,
            "grpcSettings": {"serviceName": config.service_name},
        }
        if security == "tls":
            stream["tlsSettings"] = _tls_settings(config)
        elif security == "reality":
            stream["realitySettings"] = _reality_settings(config)
        return stream

    # tcp (default) and everything else
    if security == "reality":
        return {
            "network": "tcp",
            "security": "reality",
            "realitySettings": _reality_settings(config),
        }

    if security == "tls":
        return {
            "network": "tcp",
            "security": "tls",
            "tlsSettings": _tls_settings(config),
        }

    return {
        "network": "tcp",
        "tcpSettings": {
            "header": {"type": config.header_type or "none"},
        },
    }


def _reality_settings(config: VlessConfig) -> dict:
    return {
        "serverName": config.sni,
        "fingerprint": config.fp,
        "publicKey": config.pbk,
        "shortId": config.sid,
        "spiderX": config.spx,
    }


def _tls_settings(config: VlessConfig) -> dict:
    tls: dict = {
        "serverName": config.sni,
        "fingerprint": config.fp,
    }
    if config.alpn:
        tls["alpn"] = [a.strip() for a in config.alpn.split(",")]
    return tls


def generate_xray_config(config: VlessConfig, local_port: int) -> dict:
    user: dict = {
        "id": config.uuid,
        "encryption": "none",
    }
    if config.flow:
        user["flow"] = config.flow

    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "listen": settings.PROXY_BIND_HOST,
                "port": local_port,
                "protocol": "socks",
                "settings": {"udp": True},
            }
        ],
        "outbounds": [
            {
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": config.host,
                            "port": config.port,
                            "users": [user],
                        }
                    ]
                },
                "streamSettings": _build_stream_settings(config),
            }
        ],
    }


def write_xray_config(
    config: VlessConfig, local_port: int, config_dir: str
) -> str:
    os.makedirs(config_dir, exist_ok=True)
    path = os.path.join(config_dir, f"proxy_{local_port}.json")
    data = generate_xray_config(config, local_port)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return path


# ---------------------------------------------------------------------------
# Process management
# ---------------------------------------------------------------------------

class XrayProcess:
    def __init__(
        self,
        proxy_id: int,
        local_port: int,
        config_path: str,
        storage: Storage,
    ) -> None:
        self._proxy_id = proxy_id
        self._local_port = local_port
        self._config_path = config_path
        self._storage = storage
        self._proc: asyncio.subprocess.Process | None = None
        self._pid: int | None = None

    @property
    def pid(self) -> int | None:
        return self._pid

    @property
    def local_port(self) -> int:
        return self._local_port

    async def start(self) -> int:
        self._proc = await asyncio.create_subprocess_exec(
            settings.XRAY_BINARY,
            "run",
            "-config",
            self._config_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._pid = self._proc.pid
        logger.info(
            "xray started: proxy_id=%d local_port=%d pid=%d",
            self._proxy_id,
            self._local_port,
            self._pid,
        )
        asyncio.create_task(self._monitor())
        return self._pid

    async def _monitor(self) -> None:
        if self._proc is None:
            return
        await self._proc.wait()
        returncode = self._proc.returncode
        logger.warning(
            "xray process exited: proxy_id=%d local_port=%d pid=%d returncode=%s",
            self._proxy_id,
            self._local_port,
            self._pid,
            returncode,
        )
        await self._storage.set_process_pid(self._proxy_id, None, "crashed")

    async def stop(self) -> None:
        if self._proc is None or self._proc.returncode is not None:
            return

        logger.info(
            "stopping xray: proxy_id=%d local_port=%d pid=%d",
            self._proxy_id,
            self._local_port,
            self._pid,
        )
        try:
            self._proc.send_signal(signal.SIGTERM)
            await asyncio.wait_for(self._proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning(
                "xray did not exit after SIGTERM, sending SIGKILL: pid=%d", self._pid
            )
            self._proc.kill()
            await self._proc.wait()

        if os.path.exists(self._config_path):
            os.remove(self._config_path)

    async def is_alive(self) -> bool:
        if self._pid is None:
            return False
        try:
            os.kill(self._pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False


# ---------------------------------------------------------------------------
# Process pool
# ---------------------------------------------------------------------------

class XrayProcessPool:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage
        self._processes: dict[int, XrayProcess] = {}

    async def start_proxy(
        self, proxy_id: int, config: VlessConfig
    ) -> XrayProcess | None:
        port = await self._storage.get_available_port()
        if port is None:
            logger.warning("no available port in pool for proxy_id=%d", proxy_id)
            return None

        config_path = write_xray_config(config, port, settings.XRAY_CONFIG_DIR)
        await self._storage.upsert_process(proxy_id, port, config_path)

        proc = XrayProcess(proxy_id, port, config_path, self._storage)
        pid = await proc.start()
        await self._storage.set_process_pid(proxy_id, pid, "running")

        self._processes[proxy_id] = proc
        return proc

    async def stop_proxy(self, proxy_id: int) -> None:
        proc = self._processes.pop(proxy_id, None)
        if proc is None:
            return
        await proc.stop()
        await self._storage.set_process_pid(proxy_id, None, "stopped")

    async def stop_all(self) -> None:
        for proxy_id in list(self._processes.keys()):
            await self.stop_proxy(proxy_id)

    async def restart_proxy(self, proxy_id: int, config: VlessConfig) -> None:
        await self.stop_proxy(proxy_id)
        await self.start_proxy(proxy_id, config)

    def get_process(self, proxy_id: int) -> XrayProcess | None:
        return self._processes.get(proxy_id)

    def get_all_ports(self) -> dict[int, int]:
        return {
            proxy_id: proc.local_port
            for proxy_id, proc in self._processes.items()
        }
