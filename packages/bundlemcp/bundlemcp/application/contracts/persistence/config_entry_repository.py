from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.repository import Repository
from bundlemcp.domain.config.config_entry import ConfigEntry


@runtime_checkable
class ConfigEntryRepository(Repository[ConfigEntry], Protocol):
    """Stored overrides of the runtime-tunable settings, keyed by setting name."""

    async def all(self) -> list[ConfigEntry]:
        """Every stored override."""
        ...
