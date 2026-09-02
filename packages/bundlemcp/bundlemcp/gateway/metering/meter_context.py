from pydantic import BaseModel, ConfigDict, Field


class MeterContext(BaseModel):
    """What the metering hook is told about a single tool call."""

    model_config = ConfigDict(frozen=True)

    sub: str | None = Field(
        description="Caller identity: a user id, 'api_key:<id>', or None when anonymous"
    )
    email: str | None = Field(description="Caller email when the identity provider supplied one")
    endpoint: str = Field(description="Endpoint the call arrived on")
    bundle: str = Field(description="Bundle the endpoint exposes")
    server: str = Field(description="Upstream server the call is routed to")
    tool: str = Field(description="Upstream tool name, without the bundle prefix")
    idempotency_key: str = Field(
        description="Stable key for one client invocation; internal retries reuse it, "
        "so the hook can charge exactly once",
    )
