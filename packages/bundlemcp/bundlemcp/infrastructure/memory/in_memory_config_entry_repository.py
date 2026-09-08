from bundlemcp.domain.config.config_entry import ConfigEntry
from bundlemcp.infrastructure.memory.in_memory_repository import InMemoryRepository


class InMemoryConfigEntryRepository(InMemoryRepository[ConfigEntry]):
    def __init__(self) -> None:
        super().__init__(key=lambda entry: entry.key)

    async def all(self) -> list[ConfigEntry]:
        return self.rows
