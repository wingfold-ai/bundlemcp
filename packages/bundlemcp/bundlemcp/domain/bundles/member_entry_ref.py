from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.servers.member_entry_kind import MemberEntryKind


class MemberEntryRef(BaseModel):
    """Which member entry a live listing item is: its kind, its server and its name or URI."""

    model_config = ConfigDict(frozen=True)

    kind: MemberEntryKind = Field(description="Whether it is a prompt or a resource")
    server_name: str = Field(description="The member server that lists it")
    key: str = Field(description="The prompt's name, or the resource's URI, as the member lists it")
