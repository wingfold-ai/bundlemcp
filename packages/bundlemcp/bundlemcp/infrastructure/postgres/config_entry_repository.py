from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.domain.config.config_entry import ConfigEntry
from bundlemcp.infrastructure.postgres.rows.config_entry_row import ConfigEntryRow
from bundlemcp.infrastructure.postgres.sqlalchemy_repository import SqlAlchemyRepository


class SqlAlchemyConfigEntryRepository(SqlAlchemyRepository[ConfigEntry, ConfigEntryRow]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ConfigEntry, ConfigEntryRow, key=lambda entry: entry.key)
