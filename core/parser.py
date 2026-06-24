import ipaddress
import uuid as uuid_module
from dataclasses import dataclass
from urllib.parse import parse_qs, parse_qsl, unquote, urlencode, urlparse, urlunparse


@dataclass
class VlessConfig:
    uuid: str
    host: str
    port: int
    raw_uri: str
    name: str = ""

    # Transport
    type: str = "tcp"
    security: str = "none"
    flow: str = ""
    header_type: str = "none"

    # TLS
    sni: str = ""
    fp: str = ""
    alpn: str = ""

    # Reality
    pbk: str = ""
    sid: str = ""
    spx: str = ""

    # WebSocket
    path: str = "/"
    host_header: str = ""

    # gRPC
    service_name: str = ""


@dataclass
class ParseResult:
    success: bool
    raw_uri: str
    config: VlessConfig | None = None
    error: str = ""


_VALID_TRANSPORT_TYPES = {"tcp", "ws", "grpc", "http", "kcp", "quic"}
_RUSSIAN_MARKERS = {"🇷🇺", "ru", "россия"}


def _is_russian(name: str) -> bool:
    name_lower = name.lower()
    return any(marker in name_lower for marker in _RUSSIAN_MARKERS)


def _first(params: dict, key: str, default: str = "") -> str:
    values = params.get(key)
    return values[0] if values else default


def _validate_config(config: VlessConfig) -> list[str]:
    errors: list[str] = []

    try:
        uuid_module.UUID(config.uuid)
    except ValueError:
        errors.append(f"invalid UUID: {config.uuid!r}")

    if not config.host:
        errors.append("host is empty")
    else:
        try:
            ipaddress.ip_address(config.host)
        except ValueError:
            if config.host != "localhost" and "." not in config.host:
                errors.append(f"hostname {config.host!r} has no dot and is not 'localhost'")
            if any(c in config.host for c in (" ", "\t", "\n", ";")):
                errors.append(f"hostname {config.host!r} contains invalid characters")

    if not (1 <= config.port <= 65535):
        errors.append(f"port {config.port} is out of range (1–65535)")

    if config.type not in _VALID_TRANSPORT_TYPES:
        errors.append(f"unknown transport type: {config.type!r}")

    if config.type == "ws" and not config.path.startswith("/"):
        errors.append(f"WebSocket path must start with '/': {config.path!r}")

    if config.security == "reality":
        if not config.pbk:
            errors.append("security=reality requires 'pbk' (public key)")
        if not config.sni:
            errors.append("security=reality requires 'sni'")

    if config.flow == "xtls-rprx-vision" and config.security not in ("reality", "tls"):
        errors.append("flow=xtls-rprx-vision requires security=reality or security=tls")

    if _is_russian(config.name):
        errors.append("Russian server excluded")

    return errors


def parse_vless(uri: str) -> ParseResult:
    uri = uri.strip()
    if not uri.startswith("vless://"):
        return ParseResult(success=False, raw_uri=uri, error="URI must start with vless://")

    try:
        parsed = urlparse(uri)

        userinfo, _, _ = parsed.netloc.rpartition("@")
        if not userinfo:
            return ParseResult(success=False, raw_uri=uri, error="Missing UUID in URI")

        if parsed.port is None:
            return ParseResult(success=False, raw_uri=uri, error="Missing port in URI")

        params = parse_qs(parsed.query, keep_blank_values=True)

        # Strip fragment and sort params so different orderings from the same
        # subscription don't create duplicate DB entries.
        sorted_query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
        raw_uri = urlunparse(parsed._replace(query=sorted_query, fragment=""))

        config = VlessConfig(
            uuid=userinfo,
            host=parsed.hostname or "",
            port=parsed.port,
            raw_uri=raw_uri,
            name=unquote(parsed.fragment) if parsed.fragment else "",
            type=_first(params, "type", "tcp"),
            security=_first(params, "security", "none"),
            flow=_first(params, "flow", ""),
            header_type=_first(params, "headerType", "none"),
            sni=_first(params, "sni", ""),
            fp=_first(params, "fp", ""),
            alpn=_first(params, "alpn", ""),
            pbk=_first(params, "pbk", ""),
            sid=_first(params, "sid", ""),
            spx=_first(params, "spx", ""),
            path=_first(params, "path", "/"),
            host_header=_first(params, "host", ""),
            service_name=_first(params, "serviceName", ""),
        )
    except Exception as exc:
        return ParseResult(success=False, raw_uri=uri, error=f"Parse error: {exc}")

    errors = _validate_config(config)
    if errors:
        return ParseResult(success=False, raw_uri=uri, error="; ".join(errors))

    return ParseResult(success=True, raw_uri=uri, config=config)


def parse_vless_list(text: str) -> tuple[list[VlessConfig], list[ParseResult]]:
    seen: set[str] = set()
    configs: list[VlessConfig] = []
    results: list[ParseResult] = []

    for line in text.splitlines():
        line = line.strip()
        if not line or not line.startswith("vless://"):
            continue
        result = parse_vless(line)
        results.append(result)
        if result.success and result.config is not None and result.config.raw_uri not in seen:
            seen.add(result.config.raw_uri)
            configs.append(result.config)

    return configs, results
