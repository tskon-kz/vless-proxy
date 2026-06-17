from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Telegram
    TG_BOT_TOKEN: str
    TG_ALLOWED_USER_IDS: List[int] = []
    TG_NOTIFY_CHAT_ID: int | None = None
    TG_BOT_PROXY: str | None = None

    # xray
    XRAY_BINARY: str = "/usr/local/bin/xray"
    XRAY_CONFIG_DIR: str = "/tmp/vless-manager"

    # Proxy pool
    PROXY_PORT_START: int = 10800
    PROXY_PORT_END: int = 10820
    PROXY_BIND_HOST: str = "127.0.0.1"

    # Health check
    CHECK_URL: str = "https://www.linkedin.com"
    CHECK_TIMEOUT: int = 10
    CHECK_INTERVAL: int = 300
    CHECK_STARTUP_XRAY_WAIT: int = 2

    # REST API
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8888

    # Storage
    DB_PATH: str = "./state.db"

    # Subscriptions — JSON array in .env: SUBSCRIPTION_URLS=["https://...","https://..."]
    SUBSCRIPTION_URLS: List[str] = []
    SUBSCRIPTION_FETCH_INTERVAL: int = 1800  # 30 minutes
    SUBSCRIPTION_TIMEOUT: int = 30

settings = Settings()
