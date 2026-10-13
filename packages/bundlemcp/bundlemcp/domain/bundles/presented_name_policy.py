import uuid
from collections import defaultdict

from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.bundles.bundle_tool import BundleTool
from bundlemcp.domain.bundles.presented_name import PresentedName
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.tool import Tool


class NameCollision(BaseModel):
    """One name that more than one member tool of a bundle would be presented under."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="The presented name in contention")
    tool_ids: tuple[uuid.UUID, ...] = Field(description="Every tool presented under the name")
    holders: tuple[str, ...] = Field(
        description="The same tools as 'server/tool', in the order of tool_ids, for messages"
    )

    @property
    def message(self) -> str:
        return f"'{self.name}' would be presented by {' and '.join(self.holders)}"


class PresentedNamePolicy(BaseModel):
    """Which member tool of a bundle is presented under which name.

    Every tool of every member counts, whether disabled, stale or behind a
    disabled membership, because any of them can be served again without a
    name check. An override name and a prefixed name are one namespace: a
    client cannot tell them apart.
    """

    model_config = ConfigDict(frozen=True)

    servers: dict[uuid.UUID, McpServer] = Field(description="Member servers, keyed by id")
    tools: list[Tool] = Field(description="Every cached tool of the member servers")
    curations: dict[uuid.UUID, BundleTool] = Field(
        description="The bundle's curation records, keyed by tool id"
    )

    def presented_name(self, tool: Tool) -> str:
        curation = self.curations.get(tool.id)
        return PresentedName.for_tool(
            self.servers[tool.server_id].name,
            tool.name,
            curation.override_name if curation is not None else None,
        )

    def collisions(self, involving: set[uuid.UUID]) -> list[NameCollision]:
        """The names claimed twice where at least one claimant is one of ``involving``.

        Collisions among other tools are left out, so a write is refused only
        for a conflict it would itself create or keep.
        """
        claims: dict[str, list[Tool]] = defaultdict(list)
        for tool in self.tools:
            claims[self.presented_name(tool)].append(tool)
        return [
            NameCollision(
                name=name,
                tool_ids=tuple(tool.id for tool in holders),
                holders=tuple(f"{self.servers[t.server_id].name}/{t.name}" for t in holders),
            )
            for name, holders in claims.items()
            if len(holders) > 1 and any(tool.id in involving for tool in holders)
        ]
