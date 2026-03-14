"""Application configuration via Pydantic Settings.

All configuration is loaded from environment variables (or .env file).
Secrets use SecretStr to prevent accidental logging.
"""

from __future__ import annotations

from enum import Enum

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class TradingMode(str, Enum):
    """Trading execution mode."""

    PAPER = "paper"
    LIVE = "live"


class LogLevel(str, Enum):
    """Application log level."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All values can be overridden via env vars or .env file.
    SecretStr fields will never be printed in logs.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- Polymarket ---
    polymarket_private_key: SecretStr = SecretStr("")
    polymarket_funder_address: str = ""
    polymarket_chain_id: int = 137  # Polygon mainnet
    polymarket_signature_type: int = 0  # 0=EOA

    # --- Database ---
    database_url: str = "postgresql+asyncpg://copypoly:copypoly@db:5432/copypoly"

    # --- Notifications ---
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_chat_id: str = ""

    # --- App ---
    log_level: LogLevel = LogLevel.INFO
    trading_mode: TradingMode = TradingMode.PAPER

    # --- Data Collection Intervals ---
    leaderboard_update_interval_minutes: int = 5
    position_check_interval_seconds: int = 30
    market_sync_interval_minutes: int = 15

    @property
    def database_url_sync(self) -> str:
        """Return a synchronous database URL (for Alembic)."""
        return self.database_url.replace("+asyncpg", "")


# Singleton — import this everywhere
settings = Settings()
