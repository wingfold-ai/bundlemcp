"""The bootstrap document's former key for upstream servers, still accepted while it moves."""

from typing import Any

FORMER_KEY = "servers"
KEY = "upstreams"


def accept_former_key(data: Any) -> Any:
    """Read a mapping's ``servers`` list as ``upstreams``; refuse a mapping that has both.

    Both keys at once could mean two different lists, and the document is
    rejected rather than having one of them silently win.
    """
    if not isinstance(data, dict) or FORMER_KEY not in data:
        return data
    if KEY in data:
        raise ValueError(f"use '{KEY}' only; '{FORMER_KEY}' is its former name (BOOT-8)")
    renamed = dict(data)
    renamed[KEY] = renamed.pop(FORMER_KEY)
    return renamed


def former_key_uses(data: Any) -> list[str]:
    """Where a raw document still uses the former key: the top level, and bundles by name."""
    if not isinstance(data, dict):
        return []
    uses = ["document"] if FORMER_KEY in data else []
    for bundle in data.get("bundles") or []:
        if isinstance(bundle, dict) and FORMER_KEY in bundle:
            uses.append(f"bundle {bundle.get('name', '?')}")
    return uses
