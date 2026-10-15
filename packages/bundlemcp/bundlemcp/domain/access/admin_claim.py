"""Whether an identity token's claims carry the configured admin value."""

from collections.abc import Mapping
from typing import Any


def claim_at(claims: Mapping[str, Any], path: str) -> Any:
    """The claim a dotted ``path`` names, reaching into nested objects; None when absent."""
    value: Any = claims
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return None
        value = value[part]
    return value


def carries_admin_value(claims: Mapping[str, Any], path: str, admin_value: str) -> bool:
    """The claim at ``path`` equals ``admin_value``, or is a list that contains it."""
    value = claim_at(claims, path)
    if isinstance(value, str):
        return value == admin_value
    if isinstance(value, list | tuple):
        return admin_value in value
    return False
