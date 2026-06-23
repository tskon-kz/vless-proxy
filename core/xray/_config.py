import json
import os

from config import settings
from core.parser import VlessConfig


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


def _apply_security(stream: dict, config: VlessConfig) -> dict:
    if config.security == "tls":
        stream["tlsSettings"] = _tls_settings(config)
    elif config.security == "reality":
        stream["realitySettings"] = _reality_settings(config)
    return stream


def _build_stream_settings(config: VlessConfig) -> dict:
    security = config.security
    net = config.type

    if net == "ws":
        return _apply_security({
            "network": "ws",
            "security": security,
            "wsSettings": {
                "path": config.path,
                "headers": {"Host": config.host_header} if config.host_header else {},
            },
        }, config)

    if net == "grpc":
        return _apply_security({
            "network": "grpc",
            "security": security,
            "grpcSettings": {"serviceName": config.service_name},
        }, config)

    # tcp (default) and everything else
    if security == "reality":
        return {"network": "tcp", "security": "reality", "realitySettings": _reality_settings(config)}
    if security == "tls":
        return {"network": "tcp", "security": "tls", "tlsSettings": _tls_settings(config)}
    return {"network": "tcp", "tcpSettings": {"header": {"type": config.header_type or "none"}}}


def _generate_xray_config(config: VlessConfig, local_port: int) -> dict:
    user: dict = {"id": config.uuid, "encryption": "none"}
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
                "settings": {"vnext": [{"address": config.host, "port": config.port, "users": [user]}]},
                "streamSettings": _build_stream_settings(config),
            }
        ],
    }


def write_xray_config(config: VlessConfig, local_port: int, config_dir: str) -> str:
    os.makedirs(config_dir, exist_ok=True)
    path = os.path.join(config_dir, f"proxy_{local_port}.json")
    with open(path, "w") as f:
        json.dump(_generate_xray_config(config, local_port), f, indent=2)
    return path
