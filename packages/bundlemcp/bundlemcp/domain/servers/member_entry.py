import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from bundlemcp.domain.servers.member_entry_kind import MemberEntryKind


class MemberEntry(BaseModel):
    """A member's prompt or resource as discovery last saw it, cached for curation only.

    Only what a curation screen shows is kept: the name or URI, title and
    description, never prompt messages or resource content. Endpoints keep
    serving these lists live from the member.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Identifier of the entry")
    server_id: uuid.UUID = Field(description="Server that lists the entry")
    kind: MemberEntryKind = Field(description="Whether the entry is a prompt or a resource")
    key: str = Field(description="The prompt's name, or the resource's URI, as the server lists it")
    name: str = Field(description="Its listed name; for a prompt the same as the key")
    title: str | None = Field(default=None, description="Title the server reports")
    description: str | None = Field(default=None, description="Description the server reports")
    entry_hash: str = Field(
        description="Hash of what is cached, so an unchanged entry costs no write on re-probe"
    )
    stale_since: datetime | None = Field(
        default=None,
        description="When a successful discovery first stopped listing the entry; None while "
        "the server lists it. A stale entry keeps its curation",
    )

    @property
    def is_stale(self) -> bool:
        return self.stale_since is not None
