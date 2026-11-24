"""Runtime config routes; values are consumed via RuntimeConfig."""

from typing import Any

from fastapi import status

from bundlemcp.api.http.route import route
from bundlemcp.api.http.service_providers import ConfigServiceProvider
from bundlemcp.api.management.controllers.management_controller import ManagementController
from bundlemcp.application.schemas import ConfigEntryRead, ConfigValue
from bundlemcp.domain.access.api_key_scope import FULL, ApiKeyScope


class ConfigController(ManagementController):
    prefix = "/config"
    tags = ("config",)

    @route.get("", access=ApiKeyScope.READ)
    async def get_config(self, service: ConfigServiceProvider) -> dict[str, Any]:
        return await service.effective()

    @route.put("/{key}", access=FULL)
    async def set_config(
        self, key: str, body: ConfigValue, service: ConfigServiceProvider
    ) -> ConfigEntryRead:
        return await service.set(key, body.value)

    @route.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT, access=FULL)
    async def reset_config(self, key: str, service: ConfigServiceProvider) -> None:
        await service.reset(key)
