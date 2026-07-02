"""Runtime config routes (spec 02 Config; values consumed via RuntimeConfig)."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from sqlmodel import select

from bundlemcp.api.deps import DbDep, RedisDep, ServiceAuthDep
from bundlemcp.gateway.runtime_config import DEFAULTS, UnknownConfigKey, coerce
from bundlemcp.models import ConfigEntry
from bundlemcp.store.invalidation import InvalidationEvent, publish_invalidation

router = APIRouter(prefix="/config", tags=["config"])


class ConfigValue(BaseModel):
    value: Any


@router.get("")
async def get_config(request: Request, db: DbDep, _auth: ServiceAuthDep) -> dict[str, Any]:
    """Effective config: defaults overlaid with stored overrides."""
    rows = (await db.execute(select(ConfigEntry))).scalars().all()
    overrides = {r.key: r.value for r in rows if r.key in DEFAULTS}
    return {key: overrides.get(key, default) for key, (default, _t) in DEFAULTS.items()}


@router.put("/{key}")
async def set_config(
    key: str, body: ConfigValue, db: DbDep, redis: RedisDep, _auth: ServiceAuthDep
) -> dict[str, Any]:
    try:
        value = coerce(key, body.value)
    except UnknownConfigKey:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"unknown config key (known: {sorted(DEFAULTS)})"
        ) from None
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None

    row = (
        await db.execute(select(ConfigEntry).where(ConfigEntry.key == key))
    ).scalar_one_or_none()
    if row is None:
        row = ConfigEntry(key=key, value=value)
    else:
        row.value = value
    db.add(row)
    await db.commit()
    await publish_invalidation(
        redis, InvalidationEvent(entity_type="config", key=key, action="updated")
    )  # STP-1
    return {key: value}


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def reset_config(key: str, db: DbDep, redis: RedisDep, _auth: ServiceAuthDep) -> None:
    """Remove the override; the default applies again."""
    if key not in DEFAULTS:
        return
    row = (
        await db.execute(select(ConfigEntry).where(ConfigEntry.key == key))
    ).scalar_one_or_none()
    if row is not None:
        await db.delete(row)
        await db.commit()
        await publish_invalidation(
            redis, InvalidationEvent(entity_type="config", key=key, action="deleted")
        )
