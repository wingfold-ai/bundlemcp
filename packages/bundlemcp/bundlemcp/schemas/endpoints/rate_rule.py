from pydantic import BaseModel, Field


class RateRule(BaseModel):
    limit: int = Field(gt=0)
    window_seconds: int = Field(gt=0)
