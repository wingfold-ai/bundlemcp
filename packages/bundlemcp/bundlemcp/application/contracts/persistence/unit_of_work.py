"""One transaction over the durable store, and the events that follow it."""

from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.api_key_repository import ApiKeyRepository
from bundlemcp.application.contracts.persistence.audit_repository import AuditRepository
from bundlemcp.application.contracts.persistence.authorization_code_repository import (
    AuthorizationCodeRepository,
)
from bundlemcp.application.contracts.persistence.bundle_repository import BundleRepository
from bundlemcp.application.contracts.persistence.config_entry_repository import (
    ConfigEntryRepository,
)
from bundlemcp.application.contracts.persistence.consent_repository import ConsentRepository
from bundlemcp.application.contracts.persistence.curation_repository import CurationRepository
from bundlemcp.application.contracts.persistence.endpoint_repository import EndpointRepository
from bundlemcp.application.contracts.persistence.invalidation_event import InvalidationEvent
from bundlemcp.application.contracts.persistence.membership_repository import MembershipRepository
from bundlemcp.application.contracts.persistence.oauth_client_repository import (
    OAuthClientRepository,
)
from bundlemcp.application.contracts.persistence.oauth_token_repository import OAuthTokenRepository
from bundlemcp.application.contracts.persistence.server_repository import ServerRepository
from bundlemcp.application.contracts.persistence.tool_repository import ToolRepository
from bundlemcp.application.contracts.persistence.upstream_client_repository import (
    UpstreamClientRepository,
)
from bundlemcp.application.contracts.persistence.upstream_token_repository import (
    UpstreamTokenRepository,
)
from bundlemcp.application.contracts.persistence.user_repository import UserRepository


@runtime_checkable
class UnitOfWork(Protocol):
    """A transaction whose commit also announces what changed.

    Services stage writes through the repositories, queue the invalidation
    events those writes imply, and commit. Inside an ``atomic`` scope inner
    commits are deferred to the scope's exit, so a bootstrap document lands
    all or nothing.
    """

    @property
    def servers(self) -> ServerRepository: ...
    @property
    def tools(self) -> ToolRepository: ...
    @property
    def bundles(self) -> BundleRepository: ...
    @property
    def memberships(self) -> MembershipRepository: ...
    @property
    def curations(self) -> CurationRepository: ...
    @property
    def endpoints(self) -> EndpointRepository: ...
    @property
    def api_keys(self) -> ApiKeyRepository: ...
    @property
    def users(self) -> UserRepository: ...
    @property
    def oauth_clients(self) -> OAuthClientRepository: ...
    @property
    def oauth_tokens(self) -> OAuthTokenRepository: ...
    @property
    def authorization_codes(self) -> AuthorizationCodeRepository: ...
    @property
    def consents(self) -> ConsentRepository: ...
    @property
    def upstream_clients(self) -> UpstreamClientRepository: ...
    @property
    def upstream_tokens(self) -> UpstreamTokenRepository: ...
    @property
    def config_entries(self) -> ConfigEntryRepository: ...
    @property
    def audit_records(self) -> AuditRepository: ...

    def invalidate(self, event: InvalidationEvent) -> None:
        """Queue an event to publish once the enclosing commit succeeds."""
        ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...

    def atomic(self) -> AbstractAsyncContextManager[None]:
        """Defer every commit inside the block to the block's successful exit."""
        ...

    async def refresh(self, entity: Any) -> None:
        """Reload an entity's stored state after a commit, so generated values are present."""
        ...


@runtime_checkable
class UnitOfWorkFactory(Protocol):
    """Opens a fresh unit of work per request, background task or bootstrap run."""

    def open(self) -> AbstractAsyncContextManager[UnitOfWork]: ...
