from collections.abc import Callable
from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.domain.oauth.oauth_client import OAuthClient


@runtime_checkable
class ClientSource(Protocol):
    """One way a client_id may be turned into a client.

    Sources are tried in order by the resolver; the first that handles the
    identifier answers for it. Adding a new way clients identify themselves
    means one new source, not a change to the resolver.
    """

    def handles(self, client_id: str) -> bool:
        """Whether identifiers of this shape are this source's to answer."""
        ...

    async def resolve(self, client_id: str) -> OAuthClient | None:
        """The client, or None when it is unknown.

        Raises InvalidInputError when the identifier names something that
        exists but may not act as a client of this gateway.
        """
        ...


# Builds a source over one request's transaction. The composition root lists
# the ways clients may identify themselves; a provider instantiates them.
ClientSourceFactory = Callable[[UnitOfWork], ClientSource]
