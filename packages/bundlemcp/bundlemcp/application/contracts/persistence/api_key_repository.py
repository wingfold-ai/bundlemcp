from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.page_slice import PageSlice
from bundlemcp.application.contracts.persistence.repository import Repository
from bundlemcp.domain.access.api_key import ApiKey
from bundlemcp.domain.access.api_key_kind import ApiKeyKind


@runtime_checkable
class ApiKeyRepository(Repository[ApiKey], Protocol):
    """API keys, stored as hashes."""

    async def by_hash(self, key_hash: str) -> ApiKey | None:
        """The key whose secret hashes to this value, or None."""
        ...

    async def any_of_kind(self, kind: ApiKeyKind) -> ApiKey | None:
        """Some key of this kind, or None when none exists."""
        ...

    async def page(self, *, offset: int, limit: int) -> PageSlice[ApiKey]:
        """One page in creation order, plus the total."""
        ...
