"""Shared DTO name validation."""

import re

from bundlemcp.models import NAME_PATTERN

_name_re = re.compile(NAME_PATTERN)


def validate_name(value: str) -> str:
    if not _name_re.match(value):
        raise ValueError("name must match ^[a-zA-Z0-9_-]+$")
    return value
