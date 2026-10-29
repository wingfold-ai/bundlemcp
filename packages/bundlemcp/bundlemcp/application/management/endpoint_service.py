"""Endpoint business logic: CRUD, the profile's auth-mode rule, rate-limit config."""

import uuid

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.errors import ConflictError, InvalidInputError, NotFoundError
from bundlemcp.application.management.named_resource_service import NamedResourceService
from bundlemcp.application.management.per_user_upstream_check import PerUserUpstreamCheck
from bundlemcp.application.schemas import AvailableEndpointRead, EndpointRead, EndpointUpsert
from bundlemcp.domain.endpoints.endpoint import Endpoint
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.domain.endpoints.endpoint_resource import EndpointResource
from bundlemcp.domain.endpoints.origin_policy import default_allowed_origins
from bundlemcp.domain.endpoints.profiles.profile_catalog import ProfileCatalog
from bundlemcp.domain.endpoints.profiles.profile_rule_violation import ProfileRuleViolation
from bundlemcp.domain.shared.resource_names import endpoint_name as endpoint_name_type


class EndpointService(NamedResourceService[Endpoint, EndpointRead]):
    def __init__(self, uow: UnitOfWork, *, profiles: ProfileCatalog) -> None:
        super().__init__(
            uow,
            repo=uow.endpoints,
            read_model=EndpointRead,
            entity_type="endpoint",
            label="endpoint",
        )
        self._policy = PerUserUpstreamCheck(uow)
        self._profiles = profiles

    async def upsert(self, body: EndpointUpsert) -> EndpointRead:
        try:
            self._profiles.get(body.profile).check_auth_modes(frozenset(body.auth_modes))
        except ProfileRuleViolation as exc:
            raise InvalidInputError(str(exc)) from None
        bundle = await self._uow.bundles.by_name(body.bundle_name)
        if bundle is None:
            raise NotFoundError("bundle not found")
        await self._policy.ensure_endpoint_allowed(bundle.id, body.auth_modes)
        endpoint = await self._by_name(body.name)
        created = endpoint is None
        if endpoint is None:
            endpoint = Endpoint(name=body.name, bundle_id=bundle.id)
        endpoint.bundle_id = bundle.id
        endpoint.profile = body.profile
        endpoint.auth_modes = list(body.auth_modes)
        endpoint.rate_limit = body.rate_limit.model_dump() if body.rate_limit else None
        endpoint.enabled = body.enabled
        # a full replace: an omitted list falls back to the default for the auth modes
        endpoint.allowed_origins = (
            body.allowed_origins
            if body.allowed_origins is not None
            else default_allowed_origins(body.auth_modes)
        )
        return await self._save(endpoint, name=body.name, created=created)

    async def rename(self, name: str, new_name: str, *, force: bool) -> EndpointRead:
        """Renaming breaks every connected client's URL, so force is required."""
        if not force:
            raise ConflictError(
                "renaming an endpoint changes its public URL and breaks connected clients — "
                "retry with force=true (EP-8)"
            )
        endpoint = await self._get(name)
        return await self._rename(endpoint, new_name, endpoint_name_type)

    async def available(self, public_base: str) -> list[AvailableEndpointRead]:
        """The endpoints a signed-in person can connect a client to as themselves: every
        enabled endpoint that accepts OAuth, with the URL to paste into the client."""
        endpoints = (await self._repo.page(offset=0, limit=500)).items
        entries: list[AvailableEndpointRead] = []
        for endpoint in endpoints:
            if not endpoint.enabled or not endpoint.accepts(EndpointAuthMode.OAUTH):
                continue
            bundle = await self._uow.bundles.get(endpoint.bundle_id)
            entries.append(
                AvailableEndpointRead(
                    name=endpoint.name,
                    url=EndpointResource(public_base=public_base, endpoint_name=endpoint.name).url,
                    profile=endpoint.profile,
                    bundle_name=bundle.name if bundle else "",
                    bundle_description=bundle.description if bundle else None,
                    bundle_overview=bundle.overview if bundle else None,
                )
            )
        return sorted(entries, key=lambda e: e.name)

    async def reachable_bundle_id(self, bundle_name: str) -> uuid.UUID:
        """The bundle's id, when a signed-in person could connect a client to it.

        Reachable means the same thing as in available(): some enabled endpoint on
        the bundle accepts OAuth, so a person can reach it with their own identity.
        A bundle that has none is reported as not found rather than forbidden — a
        caller with no way in should not learn that it exists.
        """
        bundle = await self._uow.bundles.by_name(bundle_name)
        if bundle is None:
            raise NotFoundError("bundle not found")
        endpoints = (await self._repo.page(offset=0, limit=500)).items
        for endpoint in endpoints:
            if (
                endpoint.bundle_id == bundle.id
                and endpoint.enabled
                and endpoint.accepts(EndpointAuthMode.OAUTH)
            ):
                return bundle.id
        raise NotFoundError("bundle not found")
