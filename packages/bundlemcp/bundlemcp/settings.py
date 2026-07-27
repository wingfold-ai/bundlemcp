"""Deploy-time configuration via environment (BUNDLEMCP_ prefix).

Runtime-tunable settings live in the Config table, not here.
"""

from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BUNDLEMCP_", env_file=".env", extra="ignore")

    # Stores (ARC-7/ARC-8)
    database_url: str = "postgresql+asyncpg://bundlemcp:bundlemcp@localhost:5432/bundlemcp"
    redis_url: str = "redis://localhost:6379/0"

    # Public identity (DEP-1) — issuer, metadata, redirects, cookies derive from this.
    public_url: AnyHttpUrl = Field(default=AnyHttpUrl("http://localhost:8000"))

    # Trusted reverse proxies (DEP-2): X-Forwarded-* honored only from these CIDRs.
    trusted_proxies: list[str] = []

    # Egress policy (SEC-2): deny evaluated after allow; metadata ranges are
    # always blocked in code regardless of these lists.
    egress_allow_cidrs: list[str] = []
    egress_deny_cidrs: list[str] = []

    # Metering hook (MID-3): import path "module:attribute"; None = no-op.
    metering_hook: str | None = None
    metering_hook_fail_open: bool = False

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
