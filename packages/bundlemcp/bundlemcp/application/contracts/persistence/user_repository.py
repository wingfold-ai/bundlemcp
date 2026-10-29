from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.page_slice import PageSlice
from bundlemcp.application.contracts.persistence.repository import Repository
from bundlemcp.domain.access.user import User


@runtime_checkable
class UserRepository(Repository[User], Protocol):
    """Users provisioned from the identity provider."""

    async def by_subject(self, issuer: str, sub: str) -> User | None:
        """The user the identity provider knows under this issuer and subject, or None."""
        ...

    async def page(self, *, offset: int, limit: int) -> PageSlice[User]:
        """One page in creation order, plus the total."""
        ...
