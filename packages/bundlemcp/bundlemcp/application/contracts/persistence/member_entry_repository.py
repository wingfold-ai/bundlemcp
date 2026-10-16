import uuid
from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.repository import Repository
from bundlemcp.domain.servers.member_entry import MemberEntry
from bundlemcp.domain.servers.member_entry_kind import MemberEntryKind


@runtime_checkable
class MemberEntryRepository(Repository[MemberEntry], Protocol):
    """Members' prompts and resources as discovery last saw them."""

    async def for_server(self, server_id: uuid.UUID, kind: MemberEntryKind) -> list[MemberEntry]:
        """One server's cached entries of one kind."""
        ...

    async def for_servers(
        self, server_ids: Iterable[uuid.UUID], kind: MemberEntryKind
    ) -> list[MemberEntry]:
        """The cached entries of one kind of several servers."""
        ...
