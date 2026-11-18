"""The migration history this release ships, read from its own scripts."""

from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import BaseModel, ConfigDict, Field

MIGRATIONS = "bundlemcp.infrastructure.postgres:migrations"


class ShippedMigrations(BaseModel):
    """The head revision this release's code needs, and every revision it knows."""

    model_config = ConfigDict(frozen=True)

    head: str = Field(description="The newest revision in this release's migration scripts")
    known: frozenset[str] = Field(description="Every revision in this release's history")

    @classmethod
    def read(cls) -> ShippedMigrations:
        """From the scripts installed with the library, so an image cannot be told a wrong head."""
        config = Config()
        config.set_main_option("script_location", MIGRATIONS)
        scripts = ScriptDirectory.from_config(config)
        head = scripts.get_current_head()
        if head is None:
            raise RuntimeError("the shipped migrations have no head")
        return cls(head=head, known=frozenset(rev.revision for rev in scripts.walk_revisions()))

    def is_current(self, applied: str | None) -> bool:
        """Whether a database at ``applied`` is at or past this release's head.

        A revision this release does not know was written by a newer release
        (expand/contract: the newer schema still serves this code), so it counts
        as current; any known revision but the head is behind.
        """
        if applied is None:
            return False
        return applied == self.head or applied not in self.known
