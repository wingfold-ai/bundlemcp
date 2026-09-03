"""Runtime config routes; values are consumed via RuntimeConfig."""

from typing import Any

from fastapi import status

from bundlemcp.api.controllers.management_controller import ManagementController
from bundlemcp.http import route
from bundlemcp.providers import ConfigServiceProvider
from bundlemcp.schemas import ConfigEntryRead, ConfigValue


class ConfigController(ManagementController):
    prefix = "/config"
    tags = ("config",)

    @route.get("")
    async def get_config(self, service: ConfigServiceProvider) -> dict[str, Any]:
        return await service.effective()

    @route.put("/{key}")
    async def set_config(
        self, key: str, body: ConfigValue, service: ConfigServiceProvider
    ) -> ConfigEntryRead:
        return await service.set(key, body.value)

    @route.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
    async def reset_config(self, key: str, service: ConfigServiceProvider) -> None:
        await service.reset(key)
