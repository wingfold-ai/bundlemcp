"""Routes for curating a bundle's members' prompts and resources."""

import uuid

from bundlemcp.api.http.route import route
from bundlemcp.api.http.service_providers import MemberCurationServiceProvider
from bundlemcp.api.management.controllers.management_controller import ManagementController
from bundlemcp.application.schemas import MemberEntryCurationRead, MemberEntryCurationUpdate
from bundlemcp.domain.servers.member_entry_kind import MemberEntryKind


class MemberCurationController(ManagementController):
    prefix = "/bundles/{bundle}"
    tags = ("bundles",)

    @route.get("/member-prompts")
    async def list_member_prompts(
        self, bundle: str, service: MemberCurationServiceProvider
    ) -> list[MemberEntryCurationRead]:
        return await service.list(bundle, MemberEntryKind.PROMPT)

    @route.put("/member-prompts/{prompt_id}")
    async def curate_member_prompt(
        self,
        bundle: str,
        prompt_id: uuid.UUID,
        body: MemberEntryCurationUpdate,
        service: MemberCurationServiceProvider,
    ) -> MemberEntryCurationRead:
        return await service.curate(bundle, MemberEntryKind.PROMPT, prompt_id, body)

    @route.get("/member-resources")
    async def list_member_resources(
        self, bundle: str, service: MemberCurationServiceProvider
    ) -> list[MemberEntryCurationRead]:
        return await service.list(bundle, MemberEntryKind.RESOURCE)

    @route.put("/member-resources/{resource_id}")
    async def curate_member_resource(
        self,
        bundle: str,
        resource_id: uuid.UUID,
        body: MemberEntryCurationUpdate,
        service: MemberCurationServiceProvider,
    ) -> MemberEntryCurationRead:
        return await service.curate(bundle, MemberEntryKind.RESOURCE, resource_id, body)
