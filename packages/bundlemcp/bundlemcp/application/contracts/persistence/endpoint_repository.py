import uuid
from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.repository import NamedRepository
from bundlemcp.domain.endpoints.endpoint import Endpoint


@runtime_checkable
class EndpointRepository(NamedRepository[Endpoint], Protocol):
    """Endpoints, the public URLs bundles are served at."""

    async def for_bundle(self, bundle_id: uuid.UUID) -> list[Endpoint]:
        """Every endpoint exposing one bundle."""
        ...
