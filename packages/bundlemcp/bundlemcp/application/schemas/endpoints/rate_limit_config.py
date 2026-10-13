from pydantic import BaseModel, Field

from bundlemcp.application.schemas.endpoints.rate_rule import RateRule


class RateLimitConfig(BaseModel):
    """Per-endpoint rate limits. Stored as JSON on the endpoint."""

    endpoint: RateRule | None = Field(
        default=None,
        description="Limit shared by every caller of the endpoint; omit for no overall cap",
    )
    per_client: RateRule | None = Field(  # EP-6
        default=None,
        description="Limit applied per caller, keyed by OAuth user, else API key, else client IP",
    )
    include_initialize_list: bool = Field(  # EP-19
        default=False,
        description="Whether initialize and tools/list count against these limits; by default "
        "only tool calls do",
    )
    fail_closed: bool = Field(  # EP-21
        default=False,
        description="Whether requests are denied when the rate-limit store is unreachable. "
        "False keeps serving traffic unlimited during an outage",
    )
