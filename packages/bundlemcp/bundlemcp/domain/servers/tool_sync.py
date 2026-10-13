"""Reconciling what a probe saw with what is cached, writing only what changed."""

import uuid
from datetime import datetime

from bundlemcp.domain.servers.probed_tool import ProbedTool
from bundlemcp.domain.servers.tool import Tool
from bundlemcp.domain.servers.tool_schema_hash import tool_schema_hash


def sync_tools(
    server_id: uuid.UUID, existing: dict[str, Tool], probed: list[ProbedTool], now: datetime
) -> tuple[list[Tool], int]:
    """Bring the cached tools in line with the probe.

    Returns the rows to stage (new and touched) and how many definitions changed.
    A tool whose definition is unchanged only has its ``last_seen_at`` moved;
    a tool the probe no longer lists is left as it was, so it goes stale rather
    than being deleted, keeping its curation. A stale tool is still served.
    """
    staged: list[Tool] = []
    changed = 0
    for seen in probed:
        digest = tool_schema_hash(
            seen.name, seen.title, seen.description, seen.input_schema, seen.annotations
        )
        row = existing.get(seen.name)
        if row is None:
            staged.append(
                Tool(
                    server_id=server_id,
                    name=seen.name,
                    title=seen.title,
                    description=seen.description,
                    input_schema=seen.input_schema,
                    annotations=seen.annotations,
                    schema_hash=digest,
                    last_seen_at=now,
                )
            )
            changed += 1
            continue
        if row.schema_hash != digest:  # write only on change
            row.title = seen.title
            row.description = seen.description
            row.input_schema = seen.input_schema
            row.annotations = seen.annotations
            row.schema_hash = digest
            changed += 1
        row.last_seen_at = now  # vanished tools keep old last_seen_at
        staged.append(row)
    return staged, changed
