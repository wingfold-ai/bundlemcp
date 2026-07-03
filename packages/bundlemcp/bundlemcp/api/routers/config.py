"""Runtime config routes; values are consumed via RuntimeConfig.

Thin controllers: HTTP concerns only; business logic lives in ConfigService.
"""

from typing import Any

from fastapi import APIRouter, status

from bundlemcp.api.deps import ConfigServiceDep, ServiceAuthDep
from bundlemcp.api.schemas import ConfigValue

router = APIRouter(prefix="/config", tags=["config"])


@router.get("")
async def get_config(svc: ConfigServiceDep, _auth: ServiceAuthDep) -> dict[str, Any]:
    return await svc.effective()


@router.put("/{key}")
async def set_config(
    key: str, body: ConfigValue, svc: ConfigServiceDep, _auth: ServiceAuthDep
) -> dict[str, Any]:
    return await svc.set(key, body.value)


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def reset_config(key: str, svc: ConfigServiceDep, _auth: ServiceAuthDep) -> None:
    await svc.reset(key)
