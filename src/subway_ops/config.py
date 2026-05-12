"""Application configuration.

Single source of truth for runtime settings. Loads from `.env` in local dev
and from real environment variables in CI / production. Exports a module-
level `settings` singleton.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Typed access to environment configuration.

    Fields default to empty strings so importing this module never fails
    in environments where a particular credential isn't configured yet
    (e.g. CI running unit tests that don't touch FreshConnect). Code paths
    that actually need a value must check for emptiness or rely on a
    downstream client to fail loudly.
    """

    database_url: str = Field(default="", description="Postgres connection URL")
    freshconnect_api_client: str = Field(default="", description="FreshConnect client id")
    freshconnect_api_key: str = Field(default="", description="FreshConnect API key")
    app_env: Literal["dev", "prod"] = "dev"

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
