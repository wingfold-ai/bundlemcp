"""Runtime config business logic; values are consumed via RuntimeConfig."""

from typing import Any

from bundlemcp.application.contracts.persistence.invalidation_event import InvalidationEvent
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.errors import InvalidInputError, NotFoundError
from bundlemcp.application.schemas import ConfigEntryRead
from bundlemcp.domain.config.config_entry import ConfigEntry
from bundlemcp.domain.config.config_registry import DEFAULTS, coerce
from bundlemcp.domain.config.unknown_config_key import UnknownConfigKey


class ConfigService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._entries = uow.config_entries

    def _invalidate(self, key: str, action: str) -> None:
        # SES-17
        self._uow.invalidate(
            InvalidationEvent(entity_type="config", key=key, action=action)  # type: ignore[arg-type]
        )

    async def effective(self) -> dict[str, Any]:
        """Effective config: defaults overlaid with stored overrides."""
        rows = await self._entries.all()
        overrides = {r.key: r.value for r in rows if r.key in DEFAULTS}
        return {key: overrides.get(key, setting.default) for key, setting in DEFAULTS.items()}

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
