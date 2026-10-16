"""Curating a bundle's members' prompts and resources."""

import uuid

from bundlemcp.application.contracts.persistence.invalidation_event import (
    EntityType,
    InvalidationEvent,
)
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.errors import NotFoundError
from bundlemcp.application.schemas import MemberEntryCurationRead, MemberEntryCurationUpdate
from bundlemcp.domain.bundles.bundle import Bundle
from bundlemcp.domain.bundles.member_entry_curation import MemberEntryCuration
from bundlemcp.domain.bundles.presented_name import PresentedName
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.member_entry import MemberEntry
from bundlemcp.domain.servers.member_entry_kind import MemberEntryKind

# the list a change to each kind's curation alters, for the clients watching the bundle
_CHANGED_LIST: dict[MemberEntryKind, EntityType] = {
    MemberEntryKind.PROMPT: "bundle_prompt",
    MemberEntryKind.RESOURCE: "bundle_resource",
}


class MemberCurationService:
    """Lists the entries discovery cached for a bundle's members, and curates them per bundle.

    Only what the bundle presents changes: an entry is hidden or its title and
    description replaced, never its name, URI or content. A change tells the
    bundle's clients that the list changed.
    """

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def _bundle(self, name: str) -> Bundle:
        bundle = await self._uow.bundles.by_name(name)
        if bundle is None:
            raise NotFoundError("bundle not found")
        return bundle

    async def _members(self, bundle: Bundle) -> dict[uuid.UUID, McpServer]:
        memberships = sorted(
            await self._uow.memberships.for_bundle(bundle.id), key=lambda m: m.position
        )
        servers = {
            s.id: s for s in await self._uow.servers.by_ids([m.server_id for m in memberships])
        }
        return {m.server_id: servers[m.server_id] for m in memberships if m.server_id in servers}

    async def list(self, bundle_name: str, kind: MemberEntryKind) -> list[MemberEntryCurationRead]:
        """Every cached entry of the kind across the bundle's members, member order then key."""
        bundle = await self._bundle(bundle_name)
        members = await self._members(bundle)
        curations = {c.entry_id: c for c in await self._uow.member_curations.for_bundle(bundle.id)}
        rank = {server_id: index for index, server_id in enumerate(members)}
        entries = sorted(
            await self._uow.member_entries.for_servers(members, kind),
            key=lambda e: (rank[e.server_id], e.key),
        )
        return [
            self._read(entry, members[entry.server_id], curations.get(entry.id))
            for entry in entries
        ]

    async def curate(
        self,
        bundle_name: str,
        kind: MemberEntryKind,
        entry_id: uuid.UUID,
        body: MemberEntryCurationUpdate,
    ) -> MemberEntryCurationRead:
        bundle = await self._bundle(bundle_name)
        members = await self._members(bundle)
        entry = await self._uow.member_entries.get(entry_id)
        if entry is None or entry.kind is not kind or entry.server_id not in members:
            raise NotFoundError(f"no {kind.value} {entry_id} among this bundle's members")
        stored = await self._uow.member_curations.find(bundle.id, entry_id)
        curation = (
            stored or MemberEntryCuration(bundle_id=bundle.id, entry_id=entry_id)
        ).model_copy(update=body.model_dump())
        self._uow.member_curations.add(curation)
        self._uow.invalidate(
            InvalidationEvent(entity_type=_CHANGED_LIST[kind], key=bundle.name, action="updated")
        )
        await self._uow.commit()
        return self._read(entry, members[entry.server_id], curation)

    @staticmethod
    def _read(
        entry: MemberEntry, server: McpServer, curation: MemberEntryCuration | None
    ) -> MemberEntryCurationRead:
        presented = (
            PresentedName(server=server.name, name=entry.key).text
            if entry.kind is MemberEntryKind.PROMPT
            else entry.key
        )
        return MemberEntryCurationRead(
            entry_id=entry.id,
            kind=entry.kind,
            server_name=server.name,
            key=entry.key,
            presented_name=presented,
            title=entry.title,
            description=entry.description,
            stale=entry.is_stale,
            enabled=curation.enabled if curation is not None else True,
            override_title=curation.override_title if curation is not None else None,
            override_description=curation.override_description if curation is not None else None,
        )
