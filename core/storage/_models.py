import json
from dataclasses import dataclass

import aiosqlite


@dataclass
class ProxyRow:
    id: int
    raw_uri: str
    host: str
    port: int
    name: str
    security: str
    type: str
    flow: str
    params: dict
    status: str
    last_check: float | None
    latency_ms: int | None
    fail_count: int
    subscription_id: int | None = None


@dataclass
class ProcessRow:
    id: int
    proxy_id: int
    local_port: int
    pid: int | None
    config_path: str
    status: str


@dataclass
class PoolStats:
    active: int
    dead: int
    pending: int
    running_processes: int


@dataclass
class SubscriptionRow:
    id: int
    url: str
    name: str
    fetch_interval: int
    last_fetch: float | None
    last_fetch_count: int
    fail_count: int
    created_at: float
    updated_at: float


def _row_to_proxy(row: aiosqlite.Row) -> ProxyRow:
    return ProxyRow(
        id=row["id"],
        raw_uri=row["raw_uri"],
        host=row["host"],
        port=row["port"],
        name=row["name"] or "",
        security=row["security"] or "none",
        type=row["type"] or "tcp",
        flow=row["flow"] or "",
        params=json.loads(row["params_json"] or "{}"),
        status=row["status"],
        last_check=row["last_check"],
        latency_ms=row["latency_ms"],
        fail_count=row["fail_count"] or 0,
        subscription_id=row["subscription_id"],
    )


def _row_to_process(row: aiosqlite.Row) -> ProcessRow:
    return ProcessRow(
        id=row["id"],
        proxy_id=row["proxy_id"],
        local_port=row["local_port"],
        pid=row["pid"],
        config_path=row["config_path"],
        status=row["status"],
    )


@dataclass
class DownStat:
    proxy_name: str
    proxy_host: str
    down_count: int
    total_downtime_s: float


def _row_to_downstat(row: aiosqlite.Row) -> "DownStat":
    return DownStat(
        proxy_name=row["proxy_name"],
        proxy_host=row["proxy_host"],
        down_count=row["down_count"],
        total_downtime_s=row["total_downtime_s"] or 0.0,
    )


def _row_to_subscription(row: aiosqlite.Row) -> SubscriptionRow:
    return SubscriptionRow(
        id=row["id"],
        url=row["url"],
        name=row["name"] or "",
        fetch_interval=row["fetch_interval"] or 1800,
        last_fetch=row["last_fetch"],
        last_fetch_count=row["last_fetch_count"] or 0,
        fail_count=row["fail_count"] or 0,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
