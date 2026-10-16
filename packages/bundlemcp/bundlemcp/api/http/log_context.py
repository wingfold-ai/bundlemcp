"""The facts a request's log lines carry, bound as each one is resolved."""

import structlog
from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.access.caller_identity import CallerIdentity


class RequestLogFields(BaseModel):
    """The closed set of fields a request may add to its log context.

    Only identifiers, never a credential or a header value: a caller cannot
    bind anything this model does not name.
    """

    model_config = ConfigDict(extra="forbid")

    endpoint: str | None = Field(default=None, description="Endpoint the request is for")
    session_id: str | None = Field(default=None, description="MCP session the request names")
    auth_method: str | None = Field(default=None, description="Which credential authenticated")
    user_id: str | None = Field(default=None, description="Authenticated user, for OAuth")
    api_key_id: str | None = Field(default=None, description="Id of the API key used, not the key")
    server: str | None = Field(default=None, description="Upstream server a tool call goes to")
    tool: str | None = Field(default=None, description="Tool name as the client called it")


def bind_request_fields(**fields: str | None) -> None:
    """Add these fields to every later log line of the current request; None ones are skipped."""
    validated = RequestLogFields(**fields).model_dump(exclude_none=True)
    if validated:
        structlog.contextvars.bind_contextvars(**validated)


def bind_caller(identity: CallerIdentity) -> None:
    """Add who is calling: the user id or the API key id, and how they authenticated."""
    bind_request_fields(
        auth_method=identity.auth_method.value,
        user_id=identity.user_id,
        api_key_id=identity.api_key_id,
    )
