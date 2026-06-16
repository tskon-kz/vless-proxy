import logging
import os
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


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
    API_SECRET_KEY: str = ""  # required for POST /update; endpoint disabled if empty

    # Storage
    DB_PATH: str = "./state.db"

    # File watcher
    VLESS_FILE: str = "./vless.txt"
    FILE_CHECK_INTERVAL: int = 30

    def validate(self) -> None:
        if not self.TG_BOT_TOKEN:
            raise ValueError("TG_BOT_TOKEN is required")

        if not os.path.exists(self.XRAY_BINARY):
            logger.warning(
                "XRAY_BINARY not found at %s — service will start without xray (debug mode)",
                self.XRAY_BINARY,
            )

        if self.PROXY_PORT_START >= self.PROXY_PORT_END:
            raise ValueError(
                f"PROXY_PORT_START ({self.PROXY_PORT_START}) must be less than PROXY_PORT_END ({self.PROXY_PORT_END})"
            )

        if self.PROXY_PORT_END - self.PROXY_PORT_START < 1:
            raise ValueError("Proxy pool must contain at least 2 ports")


settings = Settings()
