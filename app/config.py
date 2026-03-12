"""
app/config.py
─────────────
Centralised configuration loaded from environment variables.
Using pydantic-settings so every value is type-validated at startup.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── MongoDB ──────────────────────────────────────────────
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "erp_system"

    # ── LLM ──────────────────────────────────────────────────
    llm_provider: Literal["openai", "gemini"] = "openai"

    openai_api_key: str = ""
    openai_model: str = "gpt-5.2"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-pro"

    # ── App ──────────────────────────────────────────────────
    app_env: Literal["development", "production"] = "development"
    app_port: int = 8000
    app_host: str = "0.0.0.0"
    log_level: str = "INFO"
    cors_origins: str = "*"

    # ── Security ─────────────────────────────────────────────
    api_key_header: str = "X-API-Key"
    api_secret_key: str = ""  # empty = auth disabled

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        if self.cors_origins == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton of Settings."""
    return Settings()
