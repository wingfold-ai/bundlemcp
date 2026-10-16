"""The name types every resource shares.

A name is validated once, here, so the rule cannot drift between the DTO that
creates a resource and the service that renames it. The pattern is also
enforced by Postgres CHECK constraints in the initial migration; table models
stay validation-free because SQLModel skips validators for table=True classes.
"""

from typing import Annotated

from pydantic import AfterValidator, Field, StringConstraints, TypeAdapter

NAME_PATTERN = r"^[a-zA-Z0-9_-]+$"
# Server names additionally must not contain "__", and neither may
# bundle prompt names.
# A bundle resource name may be organised in folders: segments joined by "/".
BUNDLE_RESOURCE_NAME_PATTERN = r"^[a-zA-Z0-9_-]+(/[a-zA-Z0-9_.-]+)*$"
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
# The rules a pattern cannot express are published beside it, so a client can apply
# them before submitting: a double underscore is excluded as a pattern the name must
# not match, and the reserved endpoint names, compared case-insensitively, as a list.
_no_double_underscore = Field(json_schema_extra={"not": {"pattern": "__"}})
RESERVED_NAMES_KEY = "x-reserved-names"
_not_reserved = Field(json_schema_extra={RESERVED_NAMES_KEY: sorted(RESERVED_ENDPOINT_NAMES)})


def _server_name(value: str) -> str:
    if "__" in value:
        raise ValueError("server names must not contain '__' (ARC-19/BND-2)")
    return value


def _prompt_name(value: str) -> str:
    if "__" in value:
        raise ValueError("bundle prompt names must not contain '__' (BND-19)")
    return value


def _endpoint_name(value: str) -> str:
    if value.lower() in RESERVED_ENDPOINT_NAMES:
        raise ValueError(f"'{value}' is a reserved endpoint name (EP-1)")
    return value


ResourceName = Annotated[str, _pattern]
ServerName = Annotated[str, _pattern, AfterValidator(_server_name), _no_double_underscore]
EndpointName = Annotated[str, _pattern, AfterValidator(_endpoint_name), _not_reserved]
PromptName = Annotated[str, _pattern, AfterValidator(_prompt_name), _no_double_underscore]
BundleResourceName = Annotated[str, StringConstraints(pattern=BUNDLE_RESOURCE_NAME_PATTERN)]

resource_name = TypeAdapter(ResourceName)
server_name = TypeAdapter(ServerName)
endpoint_name = TypeAdapter(EndpointName)
