"""The name types every resource shares.

A name is validated once, here, so the rule cannot drift between the DTO that
creates a resource and the service that renames it. The pattern is also
enforced by Postgres CHECK constraints in the initial migration; table models
stay validation-free because SQLModel skips validators for table=True classes.
"""

from typing import Annotated

from pydantic import AfterValidator, StringConstraints, TypeAdapter

NAME_PATTERN = r"^[a-zA-Z0-9_-]+$"
# Server names additionally must not contain "__" (DOM-4, BND-2).
RESERVED_ENDPOINT_NAMES = {
    "api",
    "oauth",
    ".well-known",
    "healthz",
    "readyz",
    "metrics",
    "docs",
    "login",
    "consent",
    "static",
}

# The pattern is a constraint, so it reaches the JSON Schema and the generated
# client; the rules a pattern cannot express stay in validators.
_pattern = StringConstraints(pattern=NAME_PATTERN)


def _server_name(value: str) -> str:
    if "__" in value:
        raise ValueError("server names must not contain '__' (DOM-4/BND-2)")
    return value


def _endpoint_name(value: str) -> str:
    if value.lower() in RESERVED_ENDPOINT_NAMES:
        raise ValueError(f"'{value}' is a reserved endpoint name (EP-1)")
    return value


ResourceName = Annotated[str, _pattern]
ServerName = Annotated[str, _pattern, AfterValidator(_server_name)]
EndpointName = Annotated[str, _pattern, AfterValidator(_endpoint_name)]

server_name = TypeAdapter(ServerName)
endpoint_name = TypeAdapter(EndpointName)
