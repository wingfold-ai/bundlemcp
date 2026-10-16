import uuid
from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.repository import Repository
from bundlemcp.domain.bundles.member_entry_curation import MemberEntryCuration


@runtime_checkable
class MemberCurationRepository(Repository[MemberEntryCuration], Protocol):
    """Per-bundle curation of members' prompts and resources."""

    async def for_bundle(self, bundle_id: uuid.UUID) -> list[MemberEntryCuration]:
        """Every member-entry curation of one bundle."""
        ...

    async def find(self, bundle_id: uuid.UUID, entry_id: uuid.UUID) -> MemberEntryCuration | None:
        """The curation of one entry in one bundle, or None."""
        ...
