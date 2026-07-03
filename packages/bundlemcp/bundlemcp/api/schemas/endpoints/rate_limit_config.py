from pydantic import BaseModel

from bundlemcp.api.schemas.endpoints.rate_rule import RateRule


class RateLimitConfig(BaseModel):
    """Per-endpoint rate limits. Stored as JSON on the endpoint."""

    endpoint: RateRule | None = None  # across all callers
    per_client: RateRule | None = None  # per resolved identity (EP-6)
    include_initialize_list: bool = False  # RATE-4: also limit initialize/tools/list
    fail_closed: bool = False  # RATE-6: deny on Redis outage instead of fail-open
