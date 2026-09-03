"""Change detection for cached upstream tool definitions."""

import hashlib
import json


def tool_schema_hash(
    name: str,
    title: str | None,
    description: str | None,
    input_schema: dict,
    annotations: dict | None,
) -> str:
    """Stable hash over the full definition; only changed hashes hit Postgres."""
    canonical = json.dumps(
        {
            "name": name,
            "title": title,
            "description": description,
            "input_schema": input_schema,
            "annotations": annotations,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
