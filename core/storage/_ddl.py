CREATE_PROXIES = """
CREATE TABLE IF NOT EXISTS proxies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_uri     TEXT NOT NULL UNIQUE,
    uuid        TEXT NOT NULL,
    host        TEXT NOT NULL,
    port        INTEGER NOT NULL,
    name        TEXT DEFAULT '',
    security    TEXT DEFAULT 'none',
    type        TEXT DEFAULT 'tcp',
    flow        TEXT DEFAULT '',
    params_json TEXT DEFAULT '{}',
    status      TEXT DEFAULT 'pending',
    last_check  REAL,
    latency_ms  INTEGER,
    fail_count  INTEGER DEFAULT 0,
    subscription_id INTEGER,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
)
"""

CREATE_PROCESSES = """
CREATE TABLE IF NOT EXISTS processes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    proxy_id    INTEGER NOT NULL REFERENCES proxies(id) ON DELETE CASCADE,
    local_port  INTEGER NOT NULL UNIQUE,
    pid         INTEGER,
    config_path TEXT NOT NULL,
    started_at  REAL,
    status      TEXT DEFAULT 'stopped'
)
"""

CREATE_SUBSCRIPTIONS = """
CREATE TABLE IF NOT EXISTS subscriptions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    url              TEXT NOT NULL UNIQUE,
    name             TEXT DEFAULT '',
    fetch_interval   INTEGER DEFAULT 1800,
    last_fetch       REAL,
    last_fetch_count INTEGER DEFAULT 0,
    fail_count       INTEGER DEFAULT 0,
    created_at       REAL NOT NULL,
    updated_at       REAL NOT NULL
)
"""

CREATE_DOWNTIME_EVENTS = """
CREATE TABLE IF NOT EXISTS downtime_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    proxy_name   TEXT NOT NULL,
    proxy_host   TEXT NOT NULL,
    went_down_at REAL NOT NULL,
    came_up_at   REAL
)
"""
