"""One SQLAlchemy transaction, and the invalidation events that must follow it."""

import asyncio
import os
import traceback
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import cached_property
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.exc import DBAPIError, IntegrityError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bundlemcp.application.contracts.persistence.invalidation_event import InvalidationEvent
from bundlemcp.application.contracts.persistence.store_conflict import StoreConflict
from bundlemcp.application.contracts.persistence.store_unavailable import StoreUnavailable
from bundlemcp.application.contracts.secret_cipher import SecretCipher
from bundlemcp.infrastructure.postgres.api_key_repository import SqlAlchemyApiKeyRepository
from bundlemcp.infrastructure.postgres.audit_repository import SqlAlchemyAuditRepository
from bundlemcp.infrastructure.postgres.authorization_code_repository import (
    SqlAlchemyAuthorizationCodeRepository,
)
from bundlemcp.infrastructure.postgres.bundle_prompt_repository import (
    SqlAlchemyBundlePromptRepository,
)
from bundlemcp.infrastructure.postgres.bundle_repository import SqlAlchemyBundleRepository
from bundlemcp.infrastructure.postgres.bundle_resource_repository import (
    SqlAlchemyBundleResourceRepository,
)
from bundlemcp.infrastructure.postgres.config_entry_repository import (
    SqlAlchemyConfigEntryRepository,
)
from bundlemcp.infrastructure.postgres.consent_repository import SqlAlchemyConsentRepository
from bundlemcp.infrastructure.postgres.curation_repository import SqlAlchemyCurationRepository
from bundlemcp.infrastructure.postgres.endpoint_repository import SqlAlchemyEndpointRepository
from bundlemcp.infrastructure.postgres.member_curation_repository import (
    SqlAlchemyMemberCurationRepository,
)
from bundlemcp.infrastructure.postgres.member_entry_repository import (
    SqlAlchemyMemberEntryRepository,
)
from bundlemcp.infrastructure.postgres.member_listing_repository import (
    SqlAlchemyMemberListingRepository,
)
from bundlemcp.infrastructure.postgres.membership_repository import (
    SqlAlchemyMembershipRepository,
)
from bundlemcp.infrastructure.postgres.oauth_client_repository import (
    SqlAlchemyOAuthClientRepository,
)
from bundlemcp.infrastructure.postgres.oauth_token_repository import (
    SqlAlchemyOAuthTokenRepository,
)
from bundlemcp.infrastructure.postgres.server_locks import ServerLocks
from bundlemcp.infrastructure.postgres.server_repository import SqlAlchemyServerRepository
from bundlemcp.infrastructure.postgres.tool_repository import SqlAlchemyToolRepository
from bundlemcp.infrastructure.postgres.upstream_client_repository import (
    SqlAlchemyUpstreamClientRepository,
)
from bundlemcp.infrastructure.postgres.upstream_token_repository import (
    SqlAlchemyUpstreamTokenRepository,
)
from bundlemcp.infrastructure.postgres.user_repository import SqlAlchemyUserRepository
from bundlemcp.infrastructure.valkey.publish_invalidation import publish_invalidation


class SqlAlchemyUnitOfWork:
    """A database session whose commit also announces what changed.

    Services stage writes and queue the invalidation events those writes imply;
    ``commit`` writes the transaction and only then publishes the events, so a
    replica can never learn about a change that was rolled back. Inside an
    ``atomic`` scope, inner commits become flushes and the scope's exit commits
    everything at once, which is how a bootstrap document lands all or nothing.
    """

    def __init__(
        self,
        session: AsyncSession,
        redis: Redis,
        *,
        cipher: SecretCipher | None = None,
        server_locks: ServerLocks | None = None,
    ) -> None:
        self._session = session
        self._redis = redis
        self._cipher = cipher  # encrypts static header values at rest; None on a keyless gateway
        self._server_locks = server_locks or ServerLocks()
        self._pending: list[InvalidationEvent] = []
        self._atomic_depth = 0
        # the servers this transaction holds, and the process-local locks to release with it
        self._locked: set[uuid.UUID] = set()
        self._local_locks: list[asyncio.Lock] = []

    @property
    def session(self) -> AsyncSession:
        """The underlying session, for adapters in this package only."""
        return self._session

    @cached_property
    def servers(self) -> SqlAlchemyServerRepository:
        return SqlAlchemyServerRepository(self._session, self._cipher)

    @cached_property
    def tools(self) -> SqlAlchemyToolRepository:
        return SqlAlchemyToolRepository(self._session)

    @cached_property
    def bundles(self) -> SqlAlchemyBundleRepository:
        return SqlAlchemyBundleRepository(self._session)

    @cached_property
    def memberships(self) -> SqlAlchemyMembershipRepository:
        return SqlAlchemyMembershipRepository(self._session)

    @cached_property
    def curations(self) -> SqlAlchemyCurationRepository:
        return SqlAlchemyCurationRepository(self._session)

    @cached_property
    def member_entries(self) -> SqlAlchemyMemberEntryRepository:
        return SqlAlchemyMemberEntryRepository(self._session)

    @cached_property
    def member_listings(self) -> SqlAlchemyMemberListingRepository:
        return SqlAlchemyMemberListingRepository(self._session)

    @cached_property
    def member_curations(self) -> SqlAlchemyMemberCurationRepository:
        return SqlAlchemyMemberCurationRepository(self._session)

    @cached_property
    def bundle_prompts(self) -> SqlAlchemyBundlePromptRepository:
        return SqlAlchemyBundlePromptRepository(self._session)

    @cached_property
    def bundle_resources(self) -> SqlAlchemyBundleResourceRepository:
        return SqlAlchemyBundleResourceRepository(self._session)

    @cached_property
    def endpoints(self) -> SqlAlchemyEndpointRepository:
        return SqlAlchemyEndpointRepository(self._session)

    @cached_property
    def api_keys(self) -> SqlAlchemyApiKeyRepository:
        return SqlAlchemyApiKeyRepository(self._session)

    @cached_property
    def users(self) -> SqlAlchemyUserRepository:
        return SqlAlchemyUserRepository(self._session)

    @cached_property
    def oauth_clients(self) -> SqlAlchemyOAuthClientRepository:
        return SqlAlchemyOAuthClientRepository(self._session)

    @cached_property
    def oauth_tokens(self) -> SqlAlchemyOAuthTokenRepository:
        return SqlAlchemyOAuthTokenRepository(self._session)

    @cached_property
    def authorization_codes(self) -> SqlAlchemyAuthorizationCodeRepository:
        return SqlAlchemyAuthorizationCodeRepository(self._session)

    @cached_property
    def consents(self) -> SqlAlchemyConsentRepository:
        return SqlAlchemyConsentRepository(self._session)

    @cached_property
    def upstream_clients(self) -> SqlAlchemyUpstreamClientRepository:
        return SqlAlchemyUpstreamClientRepository(self._session)

    @cached_property
    def upstream_tokens(self) -> SqlAlchemyUpstreamTokenRepository:
        return SqlAlchemyUpstreamTokenRepository(self._session)

    @cached_property
    def config_entries(self) -> SqlAlchemyConfigEntryRepository:
        return SqlAlchemyConfigEntryRepository(self._session)

    @cached_property
    def audit_records(self) -> SqlAlchemyAuditRepository:
        return SqlAlchemyAuditRepository(self._session)

    def invalidate(self, event: InvalidationEvent) -> None:
        self._pending.append(event)

    async def lock_server(self, server_id: uuid.UUID) -> None:
        if server_id in self._locked:
            return
        local = await self._server_locks.acquire(self._session, server_id)
        self._locked.add(server_id)
        if local is not None:
            self._local_locks.append(local)

    def release_locks(self) -> None:
        """Forget the servers this transaction held; Postgres has already let them go."""
        self._locked.clear()
        while self._local_locks:
            self._local_locks.pop().release()

    async def commit(self) -> None:
        await self._flush_repositories()
        if self._atomic_depth:
            await self._session.flush()
            return
        try:
            await self._session.commit()
        finally:
            self.release_locks()
        await self._publish_pending()

    async def rollback(self) -> None:
        self._pending.clear()
        try:
            await self._session.rollback()
        finally:
            self.release_locks()

    async def refresh(self, entity: Any) -> None:
        for repository in self._repositories():
            if repository.entity is type(entity):
                await repository.refresh(entity)
                return
        raise TypeError(f"no repository for {type(entity).__name__}")

    def _repositories(self) -> list[Any]:
        """The repositories built so far; an untouched one has nothing staged."""
        return [value for name, value in vars(self).items() if not name.startswith("_")]

    async def _flush_repositories(self) -> None:
        for repository in self._repositories():
            await repository.flush_pending()

    @asynccontextmanager
    async def atomic(self) -> AsyncIterator[None]:
        self._atomic_depth += 1
        try:
            yield
        except BaseException:
            self._atomic_depth -= 1
            if not self._atomic_depth:
                await self.rollback()
            raise
        self._atomic_depth -= 1
        if not self._atomic_depth:
            await self.commit()

    async def _publish_pending(self) -> None:
        events, self._pending = self._pending, []
        await asyncio.gather(*(publish_invalidation(self._redis, event) for event in events))


class SqlAlchemyUnitOfWorkFactory:
    """Opens a fresh unit of work per request, background task or bootstrap run."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        redis: Redis,
        *,
        cipher: SecretCipher | None = None,
    ) -> None:
        self._sessions = sessions
        self._redis = redis
        self._cipher = cipher
        self._server_locks = ServerLocks()

    @asynccontextmanager
    async def open(self) -> AsyncIterator[SqlAlchemyUnitOfWork]:
        """A unit of work; a database that cannot be reached surfaces as ``StoreUnavailable``,
        and a write refused by a uniqueness or integrity rule as ``StoreConflict``."""
        uow: SqlAlchemyUnitOfWork | None = None
        try:
            async with self._sessions() as session:
                uow = SqlAlchemyUnitOfWork(
                    session, self._redis, cipher=self._cipher, server_locks=self._server_locks
                )
                yield uow
        except IntegrityError as exc:
            raise StoreConflict(_constraint_of(exc)) from exc
        except Exception as exc:
            if is_store_outage(exc):
                raise StoreUnavailable(type(exc).__name__) from exc
            raise
        finally:
            # the session is closed, which ended its transaction and every lock it held
            if uow is not None:
                uow.release_locks()


def _constraint_of(exc: IntegrityError) -> str:
    """The name of the constraint a write broke, when the driver reports it; never a value."""
    for error in (exc.orig, getattr(exc.orig, "__cause__", None)):
        name = getattr(error, "constraint_name", None)
        if isinstance(name, str) and name:
            return name
    return "integrity constraint"


# Modules a connection failure is raised from; an OSError from anywhere else inside a
# unit of work (an upstream probe, say) is not the database's.
DRIVER_MODULES = ("sqlalchemy", "asyncpg", "aiosqlite")


def is_store_outage(exc: BaseException) -> bool:
    """Whether ``exc`` means the database could not be reached, not that a query failed."""
    if isinstance(exc, OperationalError | InterfaceError | PoolTimeout):
        return True
    if isinstance(exc, DBAPIError) and exc.connection_invalidated:
        return True
    if isinstance(exc, OSError):
        frames = traceback.extract_tb(exc.__traceback__)
        return any(
            f"{os.sep}{module}{os.sep}" in frame.filename
            for frame in frames
            for module in DRIVER_MODULES
        )
    return False
