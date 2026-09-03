"""Runtime config business logic; values are consumed via RuntimeConfig."""

from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from bundlemcp.models import ConfigEntry
from bundlemcp.schemas import ConfigEntryRead
from bundlemcp.services.config_service.config_registry import DEFAULTS, coerce
from bundlemcp.services.config_service.unknown_config_key import UnknownConfigKey
from bundlemcp.services.errors import InvalidInputError, NotFoundError
from bundlemcp.store.invalidation import InvalidationEvent, publish_invalidation


class ConfigService:
    def __init__(self, db: AsyncSession, redis: Redis) -> None:
        self._db = db
        self._redis = redis

    async def _row(self, key: str) -> ConfigEntry | None:
        return (
            await self._db.execute(select(ConfigEntry).where(ConfigEntry.key == key))
        ).scalar_one_or_none()

    async def effective(self) -> dict[str, Any]:
        """Effective config: defaults overlaid with stored overrides."""
        rows = (await self._db.execute(select(ConfigEntry))).scalars().all()
        overrides = {r.key: r.value for r in rows if r.key in DEFAULTS}
        return {key: overrides.get(key, default) for key, (default, _t) in DEFAULTS.items()}

    async def set(self, key: str, value: Any) -> ConfigEntryRead:
        try:
            coerced = coerce(key, value)
        except UnknownConfigKey:
            raise NotFoundError(f"unknown config key (known: {sorted(DEFAULTS)})") from None
        except ValueError as exc:
            raise InvalidInputError(str(exc)) from None

        row = await self._row(key)
        if row is None:
            row = ConfigEntry(key=key, value=coerced)
        else:
            row.value = coerced
        self._db.add(row)
        await self._db.commit()
        await publish_invalidation(
            self._redis, InvalidationEvent(entity_type="config", key=key, action="updated")
        )  # STP-1
        return ConfigEntryRead(key=key, value=coerced)

    async def reset(self, key: str) -> None:
        """Remove the override; the default applies again."""
        if key not in DEFAULTS:
            return
        row = await self._row(key)
        if row is not None:
            await self._db.delete(row)
            await self._db.commit()
            await publish_invalidation(
                self._redis, InvalidationEvent(entity_type="config", key=key, action="deleted")
            )
