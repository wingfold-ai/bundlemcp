"""The name types every resource DTO shares.

A name is validated once, here, so the rule cannot drift between the DTO that
creates a resource and the service that renames it.
"""

import re
from typing import Annotated

from pydantic import AfterValidator, TypeAdapter

from bundlemcp.models import NAME_PATTERN, RESERVED_ENDPOINT_NAMES

_name_re = re.compile(NAME_PATTERN)


def _resource_name(value: str) -> str:
    if not _name_re.match(value):
        raise ValueError("name must match ^[a-zA-Z0-9_-]+$")
    return value


def _server_name(value: str) -> str:
    _resource_name(value)
    if "__" in value:
        raise ValueError("server names must not contain '__' (DOM-4/BND-2)")
    return value


def _endpoint_name(value: str) -> str:
    _resource_name(value)
    if value.lower() in RESERVED_ENDPOINT_NAMES:
        raise ValueError(f"'{value}' is a reserved endpoint name (EP-1)")
    return value


ResourceName = Annotated[str, AfterValidator(_resource_name)]
ServerName = Annotated[str, AfterValidator(_server_name)]
EndpointName = Annotated[str, AfterValidator(_endpoint_name)]

server_name = TypeAdapter(ServerName)
endpoint_name = TypeAdapter(EndpointName)
