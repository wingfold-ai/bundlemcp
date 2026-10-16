import uuid

from pydantic import BaseModel, Field

from bundlemcp.domain.servers.member_entry_kind import MemberEntryKind


class MemberEntryCurationRead(BaseModel):
    """A member's prompt or resource as discovery last saw it, with how this bundle curates it."""

    entry_id: uuid.UUID = Field(
        description="Identifier of the cached entry; the path parameter of its curation route"
    )
    kind: MemberEntryKind = Field(description="'prompt' or 'resource'")
    server_name: str = Field(description="The member upstream that lists it")
    key: str = Field(
        description="The prompt's name, or the resource's URI, as the upstream lists it"
    )
    presented_name: str = Field(
        description="What clients see it as: '<upstream>__<prompt>' for a prompt, the URI for a "
        "resource"
    )
    title: str | None = Field(description="Title the upstream reports")
    description: str | None = Field(description="Description the upstream reports")
    stale: bool = Field(
        description="Whether the upstream's last successful discovery no longer listed it; its "
        "curation is kept"
    )
    enabled: bool = Field(description="Whether this bundle lists and serves it")
    override_title: str | None = Field(description="Title this bundle presents instead")
    override_description: str | None = Field(description="Description this bundle presents instead")
