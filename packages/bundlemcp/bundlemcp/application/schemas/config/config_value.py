from typing import Any

from pydantic import BaseModel, Field


class ConfigValue(BaseModel):
    """A runtime-tunable configuration value."""

    value: Any = Field(description="The value to store, coerced to the type the key declares")
