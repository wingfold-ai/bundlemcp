"""Endpoint business logic: CRUD, auth-mode/profile rules, rate-limit config."""

from bundlemcp.models import Bundle, Endpoint
from bundlemcp.schemas import EndpointRead, EndpointUpsert
from bundlemcp.schemas.resource_names import endpoint_name as endpoint_name_type
from bundlemcp.services.errors import ConflictError, NotFoundError
from bundlemcp.services.named_resource_service import NamedResourceService
from bundlemcp.services.per_user_upstream_policy import PerUserUpstreamPolicy
from bundlemcp.store import Repository, UnitOfWork


class EndpointService(NamedResourceService[Endpoint, EndpointRead]):
    def __init__(self, uow: UnitOfWork) -> None:
        super().__init__(
            uow, entity=Endpoint, read_model=EndpointRead, entity_type="endpoint", label="endpoint"
        )
        self._bundles = Repository(uow.session, Bundle)
        self._policy = PerUserUpstreamPolicy(uow)

    async def upsert(self, body: EndpointUpsert) -> EndpointRead:
        bundle = await self._bundles.by_name(body.bundle_name)
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
