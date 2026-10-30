"""A unit of work over dicts: what use-case tests run on, and the proof the ports are neutral."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from bundlemcp.application.contracts.persistence.invalidation_event import InvalidationEvent
from bundlemcp.domain.bundles.bundle import Bundle
from bundlemcp.infrastructure.memory.in_memory_api_key_repository import InMemoryApiKeyRepository
from bundlemcp.infrastructure.memory.in_memory_audit_repository import InMemoryAuditRepository
from bundlemcp.infrastructure.memory.in_memory_authorization_code_repository import (
    InMemoryAuthorizationCodeRepository,
)
from bundlemcp.infrastructure.memory.in_memory_bundle_prompt_repository import (
    InMemoryBundlePromptRepository,
)
from bundlemcp.infrastructure.memory.in_memory_bundle_resource_repository import (
    InMemoryBundleResourceRepository,
)
from bundlemcp.infrastructure.memory.in_memory_config_entry_repository import (
    InMemoryConfigEntryRepository,
)
from bundlemcp.infrastructure.memory.in_memory_consent_repository import (
    InMemoryConsentRepository,
)
from bundlemcp.infrastructure.memory.in_memory_curation_repository import (
    InMemoryCurationRepository,
)
from bundlemcp.infrastructure.memory.in_memory_endpoint_repository import (
    InMemoryEndpointRepository,
)
from bundlemcp.infrastructure.memory.in_memory_member_curation_repository import (
    InMemoryMemberCurationRepository,
)
from bundlemcp.infrastructure.memory.in_memory_member_entry_repository import (
    InMemoryMemberEntryRepository,
)
from bundlemcp.infrastructure.memory.in_memory_member_listing_repository import (
    InMemoryMemberListingRepository,
)
from bundlemcp.infrastructure.memory.in_memory_membership_repository import (
    InMemoryMembershipRepository,
)
from bundlemcp.infrastructure.memory.in_memory_oauth_client_repository import (
    InMemoryOAuthClientRepository,
)
from bundlemcp.infrastructure.memory.in_memory_oauth_token_repository import (
    InMemoryOAuthTokenRepository,
)
from bundlemcp.infrastructure.memory.in_memory_repository import InMemoryRepository
from bundlemcp.infrastructure.memory.in_memory_server_repository import InMemoryServerRepository
from bundlemcp.infrastructure.memory.in_memory_tool_repository import InMemoryToolRepository
from bundlemcp.infrastructure.memory.in_memory_upstream_client_repository import (
    InMemoryUpstreamClientRepository,
)
from bundlemcp.infrastructure.memory.in_memory_upstream_token_repository import (
    InMemoryUpstreamTokenRepository,
)
from bundlemcp.infrastructure.memory.in_memory_user_repository import InMemoryUserRepository


class InMemoryUnitOfWork:
    """Holds every repository as a dict; ``committed`` counts commits and ``published``
    collects the invalidation events a commit released, so a test can assert both."""

    def __init__(self) -> None:
        self.servers = InMemoryServerRepository()
        self.tools = InMemoryToolRepository()
        self.bundles = InMemoryRepository[Bundle]()
        self.memberships = InMemoryMembershipRepository()
        self.curations = InMemoryCurationRepository()
        self.member_entries = InMemoryMemberEntryRepository()
        self.member_listings = InMemoryMemberListingRepository()
        self.member_curations = InMemoryMemberCurationRepository()
        self.bundle_prompts = InMemoryBundlePromptRepository()
        self.bundle_resources = InMemoryBundleResourceRepository()
        self.endpoints = InMemoryEndpointRepository()
        self.api_keys = InMemoryApiKeyRepository()
        self.users = InMemoryUserRepository()
        self.oauth_clients = InMemoryOAuthClientRepository()
        self.oauth_tokens = InMemoryOAuthTokenRepository()
        self.authorization_codes = InMemoryAuthorizationCodeRepository()
        self.consents = InMemoryConsentRepository()
        self.upstream_clients = InMemoryUpstreamClientRepository()
        self.upstream_tokens = InMemoryUpstreamTokenRepository()
        self.config_entries = InMemoryConfigEntryRepository()
        self.audit_records = InMemoryAuditRepository()
        self.committed = 0
        self.published: list[InvalidationEvent] = []
        self._pending: list[InvalidationEvent] = []
        self._atomic_depth = 0
        self._server_locks: dict[uuid.UUID, asyncio.Lock] = {}
        # every caller shares this one unit of work, and a nested caller's commit is not the
        # holder's: a lock belongs to the task that took it and lasts until that task leaves
        # its outermost unit of work (see the factory)
        self._held: dict[asyncio.Task | None, dict[uuid.UUID, asyncio.Lock]] = {}

    def invalidate(self, event: InvalidationEvent) -> None:
        self._pending.append(event)

    async def lock_server(self, server_id: uuid.UUID) -> None:
        held = self._held.setdefault(asyncio.current_task(), {})
        if server_id in held:
            return
        lock = self._server_locks.setdefault(server_id, asyncio.Lock())
        await lock.acquire()
        held[server_id] = lock

    def release_locks(self) -> None:
        """Release every server lock the calling task holds."""
        for lock in self._held.pop(asyncio.current_task(), {}).values():
            lock.release()

    async def commit(self) -> None:
        if self._atomic_depth:
            return
        self.committed += 1
        self.published.extend(self._pending)
        self._pending = []

    async def rollback(self) -> None:
        self._pending.clear()

    async def refresh(self, entity: Any) -> None:
        return None

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


class InMemoryUnitOfWorkFactory:
    """Hands out the same unit of work every time, so a test sees what a use case stored.

    A server lock is released when the task that took it leaves its outermost unit of
    work, as a real unit of work would release it on close; leaving a nested one does not.
    """

    def __init__(self, uow: InMemoryUnitOfWork | None = None) -> None:
        self.uow = uow or InMemoryUnitOfWork()
        self._depth: dict[asyncio.Task | None, int] = {}

    @asynccontextmanager
    async def open(self) -> AsyncIterator[InMemoryUnitOfWork]:
        task = asyncio.current_task()
        self._depth[task] = self._depth.get(task, 0) + 1
        try:
            yield self.uow
        finally:
            self._depth[task] -= 1
            if not self._depth[task]:
                del self._depth[task]
                self.uow.release_locks()
