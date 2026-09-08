"""Loading the configuration from the environment and an optional ``.env`` file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from bundlemcp.application.settings.settings import Settings


class EnvSettings(Settings, BaseSettings):
    """The configuration as ``BUNDLEMCP_*`` environment variables supply it."""

    model_config = SettingsConfigDict(env_prefix="BUNDLEMCP_", env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> EnvSettings:
    """The process-wide settings, read from the environment once."""
    return EnvSettings()
