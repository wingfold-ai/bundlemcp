"""Runtime config business logic; values are consumed via RuntimeConfig."""

from typing import Any

from bundlemcp.models import ConfigEntry
from bundlemcp.schemas import ConfigEntryRead
from bundlemcp.services.config_service.config_registry import DEFAULTS, coerce
from bundlemcp.services.config_service.unknown_config_key import UnknownConfigKey
from bundlemcp.services.errors import InvalidInputError, NotFoundError
from bundlemcp.store import Repository, UnitOfWork
from bundlemcp.store.invalidation import InvalidationEvent


class ConfigService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._entries = Repository(uow.session, ConfigEntry)

    def _invalidate(self, key: str, action: str) -> None:
        # STP-1
        self._uow.invalidate(
            InvalidationEvent(entity_type="config", key=key, action=action)  # type: ignore[arg-type]
        )

    async def effective(self) -> dict[str, Any]:
        """Effective config: defaults overlaid with stored overrides."""
        rows = await self._entries.all()
        overrides = {r.key: r.value for r in rows if r.key in DEFAULTS}
        return {key: overrides.get(key, default) for key, (default, _t) in DEFAULTS.items()}

    async def set(self, key: str, value: Any) -> ConfigEntryRead:
        try:
            coerced = coerce(key, value)
        except UnknownConfigKey:
            raise NotFoundError(f"unknown config key (known: {sorted(DEFAULTS)})") from None
        except ValueError as exc:
            raise InvalidInputError(str(exc)) from None

        row = await self._entries.get(key)
        if row is None:
            row = ConfigEntry(key=key, value=coerced)
        else:
            row.value = coerced
        self._entries.add(row)
        self._invalidate(key, "updated")
        await self._uow.commit()
        return ConfigEntryRead(key=key, value=coerced)

    async def reset(self, key: str) -> None:
        """Remove the override; the default applies again."""
        if key not in DEFAULTS:
            return
        row = await self._entries.get(key)
        if row is None:
            return
        await self._entries.delete(row)
        self._invalidate(key, "deleted")
        await self._uow.commit()
