import ipaddress
import uuid as uuid_module
from dataclasses import dataclass, field
from urllib.parse import parse_qs, unquote, urlparse, urlunparse


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


def _first(params: dict, key: str, default: str = "") -> str:
    values = params.get(key)
    return values[0] if values else default


def parse_vless(uri: str) -> ParseResult:
    uri = uri.strip()
    if not uri.startswith("vless://"):
        return ParseResult(success=False, raw_uri=uri, error="URI must start with vless://")

    try:
        parsed = urlparse(uri)

        userinfo, _, hostinfo = parsed.netloc.rpartition("@")
        if not userinfo:
            return ParseResult(success=False, raw_uri=uri, error="Missing UUID in URI")

        raw_uuid = userinfo

        # urlparse puts IPv6 brackets in hostname, strip them
        hostname = parsed.hostname or ""
        port_val = parsed.port

        if port_val is None:
            return ParseResult(success=False, raw_uri=uri, error="Missing port in URI")

        name = unquote(parsed.fragment) if parsed.fragment else ""
        params = parse_qs(parsed.query, keep_blank_values=True)

        # Strip fragment so that server renames don't create new DB entries
        raw_uri = urlunparse(parsed._replace(fragment=""))

        config = VlessConfig(
            uuid=raw_uuid,
            host=hostname,
            port=port_val,
            raw_uri=raw_uri,
            name=name,
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

    errors = validate_config(config)
    if errors:
        return ParseResult(success=False, raw_uri=uri, error="; ".join(errors))

    return ParseResult(success=True, raw_uri=uri, config=config)


_VALID_TRANSPORT_TYPES = {"tcp", "ws", "grpc", "http", "kcp", "quic"}


def validate_config(config: VlessConfig) -> list[str]:
    errors: list[str] = []

    # UUID
    try:
        uuid_module.UUID(config.uuid)
    except ValueError:
        errors.append(f"invalid UUID: {config.uuid!r}")

    # Host
    if not config.host:
        errors.append("host is empty")
    else:
        try:
            ipaddress.ip_address(config.host)
        except ValueError:
            # Not an IP — treat as hostname
            if config.host != "localhost" and "." not in config.host:
                errors.append(f"hostname {config.host!r} has no dot and is not 'localhost'")
            if any(c in config.host for c in (" ", "\t", "\n", ";")):
                errors.append(f"hostname {config.host!r} contains invalid characters")

    # Port
    if not (1 <= config.port <= 65535):
        errors.append(f"port {config.port} is out of range (1–65535)")

    # Transport type
    if config.type not in _VALID_TRANSPORT_TYPES:
        errors.append(f"unknown transport type: {config.type!r}")

    # WebSocket path
    if config.type == "ws" and not config.path.startswith("/"):
        errors.append(f"WebSocket path must start with '/': {config.path!r}")

    # Reality requirements
    if config.security == "reality":
        if not config.pbk:
            errors.append("security=reality requires 'pbk' (public key)")
        if not config.sni:
            errors.append("security=reality requires 'sni'")

    # flow constraint
    if config.flow == "xtls-rprx-vision" and config.security not in ("reality", "tls"):
        errors.append("flow=xtls-rprx-vision requires security=reality or security=tls")

    return errors


def parse_vless_list(text: str) -> tuple[list[VlessConfig], list[ParseResult]]:
    tokens: list[str] = []
    for line in text.splitlines():
        tokens.extend(line.split())

    seen: set[tuple[str, int]] = set()
    configs: list[VlessConfig] = []
    results: list[ParseResult] = []

    for token in tokens:
        token = token.strip()
        if not token or not token.startswith("vless://"):
            continue

        result = parse_vless(token)
        results.append(result)

        if result.success and result.config is not None:
            key = (result.config.host, result.config.port)
            if key not in seen:
                seen.add(key)
                configs.append(result.config)

    return configs, results


def generate_summary(results: list[ParseResult]) -> str:
    total = len(results)
    valid = sum(1 for r in results if r.success)
    invalid = total - valid

    lines = [
        f"Обработано ссылок: {total}",
        f"✅ Валидных: {valid}",
        f"❌ Невалидных: {invalid}",
    ]

    failed = [r for r in results if not r.success]
    if failed:
        lines.append("")
        lines.append("Ошибки:")
        for r in failed:
            # Truncate raw URI for readability
            uri_preview = r.raw_uri[:60] + ("..." if len(r.raw_uri) > 60 else "")
            lines.append(f"• {uri_preview} — {r.error}")

    return "\n".join(lines)
