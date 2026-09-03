"""Runtime config routes; values are consumed via RuntimeConfig."""

from typing import Any

from fastapi import status

from bundlemcp.api.controllers.management_controller import ManagementController
from bundlemcp.providers import ConfigServiceProvider
from bundlemcp.schemas import ConfigEntryRead, ConfigValue


class ConfigController(ManagementController):
    prefix = "/config"
    tags = ("config",)

    def register(self) -> None:
        self.get("", self.get_config)
        self.put("/{key}", self.set_config)
        self.delete("/{key}", self.reset_config, status_code=status.HTTP_204_NO_CONTENT)

    async def get_config(self, service: ConfigServiceProvider) -> dict[str, Any]:
        return await service.effective()

    async def set_config(
        self, key: str, body: ConfigValue, service: ConfigServiceProvider
    ) -> ConfigEntryRead:
        return await service.set(key, body.value)

    async def reset_config(self, key: str, service: ConfigServiceProvider) -> None:
        await service.reset(key)
