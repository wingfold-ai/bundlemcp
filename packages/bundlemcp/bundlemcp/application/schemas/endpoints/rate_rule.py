from pydantic import BaseModel, Field


class RateRule(BaseModel):
    """One fixed-window rate limit."""

    limit: int = Field(gt=0, description="Requests permitted within each window")
    window_seconds: int = Field(gt=0, description="Length of the window in seconds")
