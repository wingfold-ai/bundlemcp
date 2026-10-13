"""Reconciling what a probe saw with what is cached, writing only what changed."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from bundlemcp.domain.servers.probed_tool import ProbedTool
from bundlemcp.domain.servers.tool import Tool
from bundlemcp.domain.servers.tool_schema_hash import tool_schema_hash


class ToolSync(BaseModel):
    """What one successful probe changes in a server's cached tools."""

    staged: list[Tool] = Field(
        default_factory=list,
        description="Tools to write: new, redefined, vanished or reappeared. Empty when the "
        "probe saw exactly what is cached",
    )

    @property
    def changed(self) -> int:
        """How many tools changed; each one changes the tool set clients see."""
        return len(self.staged)


def sync_tools(
    server_id: uuid.UUID, existing: dict[str, Tool], probed: list[ProbedTool], now: datetime
) -> ToolSync:
    """Bring the cached tools in line with a successful probe.

    A tool is staged only when it is new, its definition hash moved, the probe
    no longer lists it (it goes stale) or the probe lists it again (it stops
    being stale). A probe that saw exactly what is cached stages nothing. A
    vanished tool is never deleted here: it keeps its curation and is served
    again with it if it comes back.
    """
    sync = ToolSync()
    for seen in probed:
        digest = tool_schema_hash(
            seen.name, seen.title, seen.description, seen.input_schema, seen.annotations
        )
        row = existing.get(seen.name)
        if row is None:
            sync.staged.append(
                Tool(
                    server_id=server_id,
                    name=seen.name,
                    title=seen.title,
                    description=seen.description,
                    input_schema=seen.input_schema,
                    annotations=seen.annotations,
                    schema_hash=digest,
                )
            )
            continue
        if row.schema_hash == digest and not row.is_stale:
            continue
        row.title = seen.title
        row.description = seen.description
        row.input_schema = seen.input_schema
        row.annotations = seen.annotations
        row.schema_hash = digest
        row.stale_since = None
        sync.staged.append(row)
    listed = {seen.name for seen in probed}
    for name, row in existing.items():
        if name not in listed and not row.is_stale:
            row.stale_since = now
            sync.staged.append(row)
    return sync
